from langchain_core.prompts import PromptTemplate

prompt = PromptTemplate.from_template("Hello {name}")
print(prompt.format(name="world"))