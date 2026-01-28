
# pip install langchain langchain-ollama langchain-chroma chromadb 
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from wxpath.integrations.langchain.loader import WXPathLoader

# ------------------------------------------------------------------
# STEP 1: Load & Embed (Same as before)
# ------------------------------------------------------------------
print("🕷️  Crawling with wxpath...")
loader = WXPathLoader(
    expression="""
    url('https://docs.python.org/3/library/argparse.html', 
    follow=//a/@href[contains(., 'argparse')])
      /map{
          'text': string-join(//div[@role='main']//text()),
          'source': string(base-uri(.))
      }
    """,
    max_depth=1
)
docs = loader.load()

print("🔪 Splitting and Embedding...")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
splits = text_splitter.split_documents(docs)

vectorstore = Chroma.from_documents(
    documents=splits, 
    # Must use model that support embeddings (`ollama pull nomic-embed-text`)
    embedding=OllamaEmbeddings(model="nomic-embed-text"),
    collection_name="wxpath"
)
retriever = vectorstore.as_retriever()

# ------------------------------------------------------------------
# STEP 2: Define Components 
# ------------------------------------------------------------------

# A helper to join retrieved documents into a single string
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# The Prompt (Standard RAG template)
template = """You are an assistant for question-answering tasks. 
Use the following pieces of retrieved context to answer the question. 
If you don't know the answer, just say that you don't know. 
Use three sentences maximum and keep the answer concise.

Context: {context}

Question: {question}

Answer:"""
prompt = ChatPromptTemplate.from_template(template)

# The Model
llm = ChatOllama(model="gemma3")

# ------------------------------------------------------------------
# STEP 3: Build the Chain with LCEL
# ------------------------------------------------------------------
# The pipe operator (|) passes output from one component to the next.
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

# ------------------------------------------------------------------
# STEP 4: Invoke
# ------------------------------------------------------------------
query = "How do I add arguments in argparse?"
print(f"\n❓ Question: {query}")

# The chain returns a string directly because of StrOutputParser
response = rag_chain.invoke(query)

print(f"\n🤖 Ollama Answer:\n{response}")