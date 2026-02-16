import os
import json
import random
from dotenv import load_dotenv

#LangChain 핵심 구성요소
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.runnables import RunnablePassthrough

from langchain_community.document_loaders import DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

import networkx as nx

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

class Choice(BaseModel):
    text : str = Field(description="option text")
    edge_feature : str = Field(description="tendency of option")
    next_node_prompt : str = Field(description="prompt for the next scene")

class Features(BaseModel):
    mood : str = Field(description="tite of scene")
    morality_impact : str = Field(description="morality impact of scene")

class StoryNode(BaseModel):
    title : str = Field(description="title of scene")
    description : str = Field(description="a full description of scene")
    features : Features = Field(description="features of the scene")
    choices : list[Choice] = Field(description="player's list of choices")


output_parser = JsonOutputParser(pydantic_object=StoryNode)

#세계관 문서 로드, 분할하여 벡터 스토어 구축
print("세계관 정보를 로드하여 RAG 메모리 구축 ....")

#문서 로드 'lore_documents 폴더의 모든 .txt 파일 로드
loader = DirectoryLoader('./lore_documents/', glob="**/*.txt")
docs = loader.load()

#문서 분할 : 로드된 문서를 500자 단위의 작은 조각으로 분할
text_splitter = RecursiveCharacterTextSplitter(chunk_size = 500, chunk_overlap = 50)
documents = text_splitter.split_documents(docs)

#벡터 스토어 생성
vector_store = FAISS.from_documents(documents, embeddings)
print("RAG 구축 완료")

#retriever 생성 (기억 검색기)
retriever = vector_store.as_retriever()

#프롬프트 템플릿 생성
#프롬프트에서 변하는 부분과 고정된 부분을 분리
template = """
your are game story writer of genius. Please be sure to refer to hte 'Key Worldview information and Past Records' provided below to create a continuous story for the current 'Request' and write language korea.
The response must be in the JSON format below.

### Important Creative Instructions ###
Whene creating a "choices" list, adjust the number of choices based on your own judgment of the importance of the given request ({request}).
- if the scene is a major turning point in the story or is very dramatic, create four or five deep choices.
- if the scene is relatively smiple situation, create only two or three choices.
- when the story progresses, try to make it fit with the content before and after as much as possible.
- please make the story into chapters.
- when creating a story, be ase detailed and thoughtful as possible.

{format_instructions}

### key worldview and past record (Context) ###
{context}

### current request (Request) ###
{request}
"""

prompt_template = PromptTemplate(
    template=template,
    input_variables=["context", "request"],
    #출력 파서에서 JSON형식을 자동으로 가져와 프롬프트에 주입
    partial_variables={"format_instructions": output_parser.get_format_instructions()}
)

#chain 결합 -LCEL(LangChain Expression Language) 사용
chain = ({"context" : retriever, "request" : RunnablePassthrough()}
         | prompt_template
         | llm
         | output_parser
         )

def make_choice_by_persona(choices, persona='hero'):
    #영웅 페르소나는 'Good' 또는 'Diplomatic' 성향의 선택지를 선호
    if persona == "hero":
        heroic_choices = [c for c in choices if c['edge_feature'] in ['Good', 'Diplomatic', 'Cautious']]
        if heroic_choices:
            return random.choice(heroic_choices)
    
    #악당 페르소나는 'Evil' 또는 'Aggressive' 성향의 선택지 선호
    elif persona == "villain":
        villainous_choices = [c for c in choices if c['edge_feature'] in ['Evil', 'Aggressive', '파괴적']]
        if villainous_choices:
            return random.choice(villainous_choices)
        
    return random.choice(choices)

def flatten_node_data(data):
    flat_data = data.copy()

    if 'features' in flat_data and isinstance(flat_data['features'], dict):
        for key, value in flat_data['features'].items():
            flat_data[f"features_{key}"] = str(value)
        del flat_data['features']

    if 'choices' in flat_data:
        del flat_data['choices']
    
    return flat_data


#example
if __name__ == "__main__":

    #비어있는 방향성 그래프 생성
    story_graph = nx.DiGraph()

    initial_prompt = "당신은 별의 제단을 지키는 '별자리의 수호자'입니다. 밤하늘을 올려다보자 사자자리(Leo)의 빛이 약해지더니, 눈앞의 평온한 계곡이 찢어지며 '그리스 신화'의 논리로 재작성되는 '리프트'가 열립니다. 강물은 스틱스처럼 검게 변하고 , 발밑의 땅에서는 탑을 건설할 수 있는 '신성한 광맥'의 맥동이 느껴집니다. 저 멀리, 리프트의 심연에서 메두사의 깨어난 석상들이 첫 번째 파동을 이루며 다가오고 있습니다."
    initial_node_id = "시작" #초기 노드의 고유ID
    story_graph.add_node(initial_node_id, title="시작", prompt=initial_prompt) #시작 노드 추가

    #현재 노드 ID 추적할 변수
    current_node_id = initial_node_id

    #100개의 노드를 생성할때까지 반복
    for _ in range(50):
        print("\n========================================================")
        print(f"장면 생성 중 .... (현재 프롬프트 : {initial_prompt})")

        try:
            #현재 프롬프트로 스토리 노드 생성
            story_node_data = chain.invoke(initial_prompt)

            #새 노드 ID로 title 사용, 기존 노드 정보 업데이트
            new_node_id = story_node_data['title']
            
            flat_node_data = flatten_node_data(story_node_data)

            story_graph.add_node(new_node_id, **flat_node_data)

            #이전 노드와 새 노드를 엣지로 연결 (선택지 정보 포함)
            #이 로직은 실제 게임에서는 어떤 선택으로 여기에 왔는지 알아야 함
            #여기서는 루프의 흐름상 연결을 보여줌
            if current_node_id != new_node_id:
                story_graph.add_edge(current_node_id, new_node_id, choice_text = "이야기 진행")

            #생성된 스토리 장면과 제목을 보여줌
            print(f"\n[ {story_node_data['title']} ]")
            print(story_node_data['description'])

            new_memory = f"[{story_node_data['title']}] {story_node_data['description']}"
            vector_store.add_texts([new_memory])
            print("\n(시스템 : 새로운 기억이 저장되었음)")

            #선택지를 번호와 함께 보여줌
            print("\n--- 선택지 ---")
            choices = story_node_data['choices']
            for i, choice in enumerate(story_node_data['choices']):
                print(f"{i + 1}. {choice['text']}")

            #각 선택지를 미래 노드를 향한 엣지로 그래프에 추가
            for choice in choices:
                #미래 노드의 ID는 간결함을 위해 다음 프롬프트의 일부 사용하거나 해시할 수 있음
                #여기서는 간단히 choice['text']로 표현
                future_node_id = choice['next_node_prompt'][:30] + "..." #간단한 ID 생성
                story_graph.add_edge(new_node_id, future_node_id, **choice)

            if not story_node_data['choices']:
                print("선택지가 없어 생성을 중단합니다.")
                break

            selected_choice = make_choice_by_persona(story_node_data['choices'], persona="hero")
            print(f"\n(시스템: 랜덤 선택 -> '{selected_choice['text']}')")

            #다음 프롬프트를 업데이트
            initial_prompt = selected_choice['next_node_prompt']
            current_node_id = new_node_id

        except (ValueError, IndexError):
            print("잘못된 입력입니다. 다시 입력해주세요.")
        except Exception as e:
            print(f"Error : {e}")
            break

        nx.write_graphml(story_graph, "story_graph.graphml")
        print(f"그래프가 'story_graph.graphml' 파일로 저장되었습니다. 노드 {len(story_graph.nodes)}개, 엣지 {len(story_graph.edges)}개")


#test code
'''
    while True:
        print("\n========================================================")
        print(f"장면 생성 중 .... (현재 프롬프트 : {initial_prompt})")

        try:
            #현재 프롬프트로 스토리 노드 생성
            story_node_data = chain.invoke(initial_prompt)

            #생성된 스토리 장면과 제목을 보여줌
            print(f"\n[ {story_node_data['title']} ]")
            print(story_node_data['description'])

            new_memory = f"[{story_node_data['title']}] {story_node_data['description']}"
            vector_store.add_texts([new_memory])
            print("\n(시스템 : 새로운 기억이 저장되었음)")

            #선택지를 번호와 함께 보여줌
            print("\n--- 선택지 ---")
            for i, choice in enumerate(story_node_data['choices']):
                print(f"{i + 1}. {choice['text']}")

            #사용자로부터 다음 행동을 입력받음
            print("\n당신의 선택은? (숫자 입력, 종료하려면 'exit' 입력) : ", end="")
            user_input = input()

            if user_input.lower() == 'exit':
                print("종료")
                break

            choice_index = int(user_input) - 1

            #선택한 'next_node_prompt'를 다음 루프의 입력으로 설정
            selected_choice = story_node_data['choices'][choice_index]
            initial_prompt = selected_choice['next_node_prompt']

        except (ValueError, IndexError):
            print("잘못된 입력입니다. 다시 입력해주세요.")
        except Exception as e:
            print(f"Error : {e}")
            break
'''
            

#test code
'''
    try:
       story_node_data = chain.invoke({"request": initial_prompt})

       print("--- 생성된 스토리 노드 (LangChain) ---")
       print(json.dumps(story_node_data, indent=2, ensure_ascii=False))

       print("--- 생성된 스토리 개수 확인 ---")
       print(f"생성된 선택지 개수 : {len(story_node_data['choices'])}")

       print("\n--- 객체 접근 ---")
       print(f"title : {story_node_data['title']}")
       print(f"first choice : {story_node_data['choices'][0]['text']}")

    except Exception as e:
        print(f"LangChain Error : {e}")
'''