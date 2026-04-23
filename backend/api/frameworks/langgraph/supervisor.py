from typing import List
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers.openai_functions import JsonOutputFunctionsParser

def create_supervisor_chain(model, members: List[str]):
    """
    Creates the supervisor chain that decides which worker to call next.
    """
    system_prompt = (
        "You are a supervisor tasked with managing a conversation between the"
        " following workers: {members}. Given the following user request,"
        " respond with the worker to act next. Each worker will perform a"
        " task and respond with their results and status. \n\n" 
        " - If the user asks to write code, edit files, or run terminal commands, choose 'Coder'.\n"
        " - If the user asks to run a specific tool (deployment, linter, custom script), choose 'ToolRunner'.\n"
        " - If the user asks a general question or the task is complete, choose 'FINISH'."
    )
    
    options = ["FINISH"] + members
    
    # Using OpenAI function calling for structured output
    function_def = {
        "name": "route",
        "description": "Select the next role.",
        "parameters": {
            "title": "routeSchema",
            "type": "object",
            "properties": {
                "next": {
                    "title": "Next",
                    "anyOf": [
                        {"enum": options},
                    ],
                }
            },
            "required": ["next"],
        },
    }
    
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
            (
                "system",
                "Given the conversation above, who should act next?"
                " Or should we FINISH? Select one of: {options}",
            ),
        ]
    ).partial(options=str(options), members=", ".join(members))
    
    return (
        prompt
        | model.bind_functions(functions=[function_def], function_call="route")
        | JsonOutputFunctionsParser()
    )
