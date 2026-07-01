import streamlit as st
from PIL import Image

from ..functions.path import pages_str, data_str, get_file_path
from ..functions.gui import create_st_button, get_neighbor_path

import pandas as pd
import uuid
import re
from random import randint
import streamlit as st
from io import BytesIO

def home_page():

	left_col, right_col = st.columns(2)

	img_dir = get_neighbor_path(__file__, pages_str, data_str)
	model_img = Image.open(get_file_path( "ai_doctor_space.png", dir_path=img_dir,))
	left_col.image(model_img, output_format="PNG")


	right_col.markdown("# Multi-Diagnostic Model")
	right_col.markdown("### An AI and knowledge graph-powered CDS tool to support multi-diagnostic medical scenarios during deep space missions")
	#right_col.markdown("**Created by Charlotte Nelson**")
	#right_col.markdown("**NASA HRP ExMC **")

	nasa_link_dict = {
		"ExMC": "https://www.nasa.gov/hrp/exmc/",
		"HRP": "https://www.nasa.gov/hrp/",
	}

	st.sidebar.markdown("## NASA Links")
	for link_text, link_url in nasa_link_dict.items():
		create_st_button(link_text, link_url, st_col=st.sidebar)



	st.markdown("---")
	left_col, right_col = st.columns(2)
	img = Image.open(get_file_path("exmc_metagraph_v1.png",dir_path=img_dir,))
	right_col.image(img, output_format="PNG")
	img = Image.open(get_file_path("multi_step_with_kg.png",dir_path=img_dir,))
	right_col.image(img, output_format="PNG")

	left_col.markdown(
		"""
		### Introduction
		As missions move beyond low Earth orbit, delayed or lack of communication with the ground 
		will require the crew members to act autonomously during critical medical situations. Though 
		crew members take mandatory medical training, it is not enough to address many of the health
		risks present in deep space missions. A potential solution is a *Clinical Decision Support 
		System (CDSS)* that could be utilized by non-medically trained crew members. Recent advances 
		in Artificial Intelligence (AI) have triggered the release of many publicly available Large 
		Language Models (LLMs). LLMs are AI systems trained on significant quantities of text data 
		and can generate human-like responses. Though LLMs can logically process text, they are prone 
		to hallucination when asked a question outside of an LLM’s training. This can be reduced by 
		training the LLM on domain-specific literature (e.g. a Medical LLM). However, a more robust 
		method to combat LLM hallucinations is to pair the LLM with a domain-specific knowledge graph 
		that connects entities through relationships. Here, we report the framework for a knowledge 
		graph and LLM-powered CDSS. 
		"""
	)


	st.markdown("---")

	st.markdown(
		"""
		### Usage

		To the left, is a dropdown main menu for navigating to 
		each crew member history and medical scenario:

		- **Home Page:** We are here!
		- **Canned EHRs:** Use pre-saved EHR data to populate the results.
		- **Interactive:** Decide the crew member's test results and symptoms.
		"""
	)

	st.markdown("---")

	st.markdown(
		"""
		### LLM Info

		Large Language Models (LLMs) are sophisticated AI models that leverage neural networks to process and generate human-quality text. Trained on vast datasets, LLMs can perform tasks like translation, summarization, and creative writing with impressive accuracy and fluency.

		- **Model Name:** Gemma2.
		- **Model Type:** Small General LLM.
		- **Number of Parameters:** 9.24B.
		- **Actions:** Tests or medical actions that the LLM can pick.
		- **Emergency Stages:** Different roles the LLM can take on.
		"""
	)





