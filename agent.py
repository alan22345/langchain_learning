from typing import List, Union
from dotenv import load_dotenv
import os
from langchain.agents import tool, Tool
from langchain.agents.output_parsers import ReActSingleInputOutputParser
from langchain.agents.format_scratchpad import format_log_to_str
from langchain.prompts import PromptTemplate
from langchain.tools.render import render_text_description
from langchain_openai import AzureOpenAI
from langchain.schema import AgentAction, AgentFinish

load_dotenv()

from callbacks import AgentCallbackHandler


# makes the function a tool to be used by langchain
@tool
def get_text_length(text: str) -> int:
    # description is important for LLM to identify whether to use function
    """Returns the length of a text by characters"""
    text = text.strip("'\n").strip('"')
    return len(text)


def find_tool_by_name(tools: List[Tool], tool_name: str) -> Tool:
    for tool in tools:
        if tool.name == tool_name:
            return tool
        raise ValueError(f"Tool with name {tool_name} not found")


if __name__ == "__main__":
    print("running agent")
    tools = [get_text_length]

    # template from langsmith  hwchase17/react
    template = """
    Answer the following questions as best you can. You have access to the following tools:

    {tools}

    Use the following format:

    Question: the input question you must answer
    Thought: you should always think about what to do
    Action: the action to take, should be one of [{tool_names}]
    Action Input: the input to the action
    Observation: the result of the action
    ... (this Thought/Action/Action Input/Observation can repeat N times)
    Thought: I now know the final answer
    Final Answer: the final answer to the original input question

    Begin!

    Question: {input}
    Thought: {agent_scratchpad}
    """
    prompt = PromptTemplate.from_template(template=template).partial(
        tools=render_text_description(tools),
        tool_names=", ".join([t.name for t in tools]),
    )

    llm = AzureOpenAI(
        temperature=0,
        model_kwargs={"stop": ["\nObservation", "Observation"]},
        callbacks=[AgentCallbackHandler()],
        deployment_name=os.environ["MY_DEPLOYMENT_NAME"],
        azure_endpoint=os.environ["MY_OPENAI_API_BASE"],
        openai_api_version=os.environ["MY_OPENAI_API_VERSION"],
        openai_api_key=os.environ["MY_OPENAI_API_KEY"],
    )
    intermediate_steps = []
    agent = (
        {
            "input": lambda x: x["input"],
            "agent_scratchpad": lambda x: x["agent_scratchpad"],
        }
        | prompt
        | llm
        | ReActSingleInputOutputParser()
    )
    agent_step = ""
    while not isinstance(agent_step, AgentFinish):

        agent_step: Union[AgentAction, AgentFinish] = agent.invoke(
            {
                "input": "What is the text length of DOG in characters?",
                "agent_scratchpad": intermediate_steps,
            }
        )
        print(agent_step)

        if isinstance(agent_step, AgentAction):
            tool_name = agent_step.tool
            tool_to_use = find_tool_by_name(tools, tool_name)
            tool_input = agent_step.tool_input

            observation = tool_to_use.func(str(tool_input))
            print(f"{observation=}")
            intermediate_steps.append(
                (agent_step.log, "Observation=" + str(observation))
            )

    if isinstance(agent_step, AgentFinish):
        print(agent_step.return_values)
