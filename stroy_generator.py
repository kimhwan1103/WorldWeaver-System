import google.generativeai as genai
import os
import json
from dotenv import load_dotenv

#LangChain 핵심 구성요소
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

#API키 설정
load_dotenv()
genai.configure(api_key=os.environ['GOOGLE_API_KEY'])

#빠른 잼민이 사용
model = genai.GenerativeModel('gemini-2.0-flash')

def generate_story_node(prompt):
    '''
    주어진 프롬프트를 바탕으로 스토리 노드와 엣지, 피쳐 생성
    '''
    #잼민이에게 JSON 형식으로 응답하도록 하여 명확하게 요청하는것이 중요
    full_prompt = f"""
    
    request : "{prompt}"

    JSON format:
    {{
        "title: : title of scene",
        "description" : "a full description of scene (2~3 paragraph)",
        "fefatures" : {{
            "mood" : "mood (example : Tense, Mysterious, Hopeful)",
            "morality_impact" : "moral influences (example : Good, Evil, Neutral)",
        }},
        "choices" : [
            {{
                "text" : "text of option 1",
                "edge_feature" : "inclination of option 1 (example : Aggressive, Diplomatic, Cautious)",
                "next_node_prompt" : "Ideas for the next scene when you choose option 1"
            }},
            {{
                "text" : "option 2 of text",
                "edge_feature" : "inclination of option 2 (example : Aggressive, Diplomatic, Cautious)",
                "next_node_prompt" : "Ideas for the next scene when you choose option 2"
            }}
            {{
                "text" : "option 3 of text",
                "edge_feature" : "inclination of option 3 (example : Aggressive, Diplomatic, Cautious)",
                "next_node_prompt" : "Ideas for the next scene when you choose option 3"
            }}
        ]
    }}
    """

    try:
        response = model.generate_content(full_prompt)
        #잼민이 응답에서 JSON 부분만 추출
        json_response = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
        return json_response
    except Exception as e:
        print(f"Error generation story or parsing JSON : {e}")



if __name__ == "__main__":
    #게임 시작 프롬프트
    initial_prompt = "플레이어가 폐허가 된 고대 사원에서 신비로운 빛을 내는 제단을 발견했습니다."

    story_node_data = generate_story_node(initial_prompt)

    if story_node_data:
        print("--- 생성된 스토리 노드 ---")
        print(json.dumps(story_node_data, indent=2, ensure_ascii=False))