import os
import tensorflow as tf

import amlrealtimeai
from amlrealtimeai import resnet50
import amlrealtimeai.resnet50.utils
from amlrealtimeai.resnet50.model import LocalQuantizedResNet50
from amlrealtimeai.pipeline import ServiceDefinition, TensorflowStage, BrainWaveStage
from amlrealtimeai import DeploymentClient
from amlrealtimeai import PredictionClient
import requests

import time 

## ---------------------------------------------------------------
## For loading a *.pb file

def load_graph(frozen_graph_filename):
	
	# We load the protobuf file from the disk and parse it to retrieve the unserialized graph_def
	with tf.gfile.GFile(frozen_graph_filename, "rb") as f:
		graph_def = tf.GraphDef()
		graph_def.ParseFromString(f.read())

	# Then, we import the graph_def into a new Graph and returns it 
	with tf.Graph().as_default() as graph:
		# The name var will prefix every op/nodes in your graph
		# Since we load everything in a new graph, this is not needed
		tf.import_graph_def(graph_def, name="prefix")
	return graph, graph_def

def printDeltaTime(text,time0):
	print("\t ++ ",text,": ", (time.time() - time0))

## ---------------------------------------------------------------

def main():

	############################################
	#### "configuration"
	deployModelAndService = False;
	brainwavePrediction = True;
	standaloneTF = True;
	############################################

	time0 = time.time()*1000
	printDeltaTime("Time 0",time0)

	# some standard setup of the resnet50
	in_images = tf.placeholder(tf.string)
	image_tensors = resnet50.utils.preprocess_array(in_images)
	print(image_tensors.shape)

	model_path = os.path.expanduser('~/models')
	model = LocalQuantizedResNet50(model_path)
	print(model.version)

	model.import_graph_def(include_featurizer=False)
	print(model.classifier_input.shape)

	# define the service	
	save_path = os.path.expanduser('~/models/save')
	service_def_path = os.path.join(save_path, 'service_def.zip')

	service_def = ServiceDefinition()
	service_def.pipeline.append(TensorflowStage(tf.Session(), in_images, image_tensors))
	service_def.pipeline.append(BrainWaveStage(model))
	service_def.pipeline.append(TensorflowStage(tf.Session(), model.classifier_input, model.classifier_output))
	service_def.save(service_def_path)
	print(service_def_path)	

	subscription_id = "80defacd-509e-410c-9812-6e52ed6a0016"
	resource_group = "CMS_FPGA_Resources"
	model_management_account = "CMS_FPGA_1"
	model_name = "resnet50-model-nvt"
	service_name = "quickstart-service"

	############# deploying new model and service #############
	if deployModelAndService:
		# some configuration
		useExistingModelAndService = True
	 
		deployment_client = DeploymentClient(subscription_id, resource_group, model_management_account)
		# at this line one should get asked for authentication
		service = deployment_client.get_service_by_name(service_name)

		# if the service and model exist don't do anything
		if not useExistingModelAndService:
			model_id = deployment_client.register_model(model_name, service_def_path)
			if(service is None):
				service = deployment_client.create_service(service_name, model_id)    
			else:
				service = deployment_client.update_service(service.id, model_id)
	############# deploying new model and service #############

	############# doing the brainwave prediction #############
	if brainwavePrediction:
		# Is this temporary?? It works for me...
		service_IP_address = "23.96.15.33";
		service_port = "80";
		#print("service IP address = ", service.ipAddress)
		#print("service port = ", service.port)

		# inference client
		client = None;
		if not deployModelAndService: client = PredictionClient(service_IP_address, service_port) # use the hard-coded numbers
		if deployModelAndService: client = PredictionClient(service.ipAddress, service.port)
		
		classes_entries = requests.get("https://raw.githubusercontent.com/Lasagne/Recipes/master/examples/resnet50/imagenet_classes.txt").text.splitlines()

		#image_file = 'jet_image.jpg'
		image_file = 'American_bison_k5680-1.jpg'
		results = client.score_image(image_file)

		# map results [class_id] => [confidence]
		results = enumerate(results)
		# sort results by confidence
		sorted_results = sorted(results, key=lambda x: x[1], reverse=True)
		# print top 5 results
		for top in sorted_results[:5]:
			print(classes_entries[top[0]], 'confidence:', top[1])
	############# doing the brainwave prediction #############

	############# standalone tf #############
	if standaloneTF:

		with open('American_bison_k5680-1.jpg', 'rb') as f:
		# with open('jet_image.jpg', 'rb') as f:
			data = f.read()
			# print(data)
			# local_image_tensors = resnet50.utils.preprocess_array(tf.constant(['jet_image.jpg']))
			local_image_tensors = resnet50.utils.preprocess_array(tf.constant([data]))
			
			# now get the featurizer pb file and load it into a graph
			# in the setup above, you download a zip file with the pb files in it in ~/models
			# unzip this file and then correct the path below
			graph, graph_def = load_graph('/Users/ntran/models/resnet50/1.1.6-rc/resnet50.pb'); 
			# graph, graph_def = load_graph('/Users/ntran/models/resnet50/1.1.6-rc/resnet50_classifier.pb');
			#for op in graph.get_operations(): print(op.name)
			x = graph.get_tensor_by_name('prefix/InputImage:0')
			y = graph.get_tensor_by_name('prefix/resnet_v1_50/pool5:0')

			sess = tf.Session()
			result = sess.run(local_image_tensors)
			print("local image tensor shape = ", local_image_tensors.shape)
			print("result shape = ", result.shape)
			print("y shape = ", y.shape)
			print("x shape = ", x.shape)
			result2 = sess.run(y, feed_dict = {x:result})
	############# standalone tf #############

if __name__ == "__main__":
	main()