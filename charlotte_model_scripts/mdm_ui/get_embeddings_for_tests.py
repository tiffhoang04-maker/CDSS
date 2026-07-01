from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import time
import os
from pathlib import Path
# python
# Use FAISS local persistence directory
VECTOR_DB_NAME = './faiss_db/'
os.makedirs(VECTOR_DB_NAME, exist_ok=True)

# Previous value pointed at a possibly read-only mount; use local path instead
# VECTOR_DB_NAME = '/mnt/nasa_test_embeddings/'
CHUNK_SIZE = 650
CHUNK_OVERLAP = 200
BATCH_SIZE = 200
SENTENCE_EMBEDDING_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'

def load_vectorstore(test_dir, file_type_list):
	vectorstore_dict = {}
	for file_type in file_type_list:
		if os.path.exists(VECTOR_DB_NAME+test_dir+'/'+file_type)==False:
			create_vectordb(test_dir, file_type)
		vectorstore_dict[file_type] = load_faiss(VECTOR_DB_NAME+test_dir+'/'+file_type, SENTENCE_EMBEDDING_MODEL)
	return vectorstore_dict

def create_vectordb(test_dir, file_type):
	start_time = time.time()
	#
	data, metadata_list = load_data(test_dir, file_type)
	print(len(data))
	#
	# doc= list of langchain documents where page_content=node name and metadata=corresponding metadata
	text_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
	docs = text_splitter.create_documents(data, metadatas=metadata_list)
	# 
	# create embeddings for each doc / node name
	# create FAISS vectorstore from all docs and save locally
	embedding_function = load_sentence_transformer(SENTENCE_EMBEDDING_MODEL)
	vectorstore = FAISS.from_documents(docs, embedding_function)
	persist_path = os.path.join(VECTOR_DB_NAME, test_dir, file_type)
	os.makedirs(persist_path, exist_ok=True)
	vectorstore.save_local(persist_path)
	end_time = round((time.time() - start_time)/(60), 2)
	print("VectorDB is created in {} mins".format(end_time))

def load_faiss(vector_db_path, sentence_embedding_model):
	embedding_function = load_sentence_transformer(sentence_embedding_model)
	# We created these files locally; allow loading pickled index for local data
	return FAISS.load_local(vector_db_path, embedding_function, allow_dangerous_deserialization=True)

def load_sentence_transformer(sentence_embedding_model):
	return SentenceTransformerEmbeddings(model_name=sentence_embedding_model)

def load_data(test_dir, file_type):
	data = load_tests(test_dir, file_type).strip().split('\n')
	source_str = " from %s" % test_dir
	metadata_list = list(map(lambda x:{"source": x + source_str}, data))
	return data, metadata_list

def load_tests(test_dir, file_type):
	text = ''
	with open('%s/%s' % (test_dir, file_type), 'r') as file:
		text = ''.join(file.readlines())
	return text



