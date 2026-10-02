import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

url = "http://100.107.139.24:1234/v1/chat/completions"
key = "sk-lm-gQhVZVvU:N4TiDU8wD38PPbK99thz"
model_name = "qwen/qwen3-4b"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Observation:
    tool_call_id: str
    tool_name: str
    result: str


@dataclass
class Step:
    action: ToolCall
    observation: Observation


@dataclass
class AgentState:
    task: str
    history: list[Step] = field(default_factory=list)


@dataclass
class ModelResponse:
    content: str | None
    tool_calls: list[ToolCall]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., object]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def execute(self, arguments: dict) -> str:
        return str(self.handler(**arguments))


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict) -> str:
        return self._tools[name].execute(arguments)


class OpenAICompatibleModel:
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model: str,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> ModelResponse:

        payload = {
            "model": self.model,
            "messages": messages,
        }

        if tools:
            payload["tools"] = tools

        print("=" * 30)
        print(payload)
        print("=" * 30)

        response = httpx.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
            trust_env=False,
        )

        response.raise_for_status()

        data = response.json()

        message = data["choices"][0]["message"]

        tool_calls = []

        for raw_call in message.get("tool_calls") or []:
            function = raw_call["function"]

            tool_calls.append(
                ToolCall(
                    id=raw_call["id"],
                    name=function["name"],
                    arguments=json.loads(function["arguments"]),
                )
            )

        return ModelResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
        )


def calculator(a: float, b: float) -> float:
    return a * b


calculator_tool = Tool(
    name="calculator",
    description="Multiply two numbers.",
    parameters={
        "type": "object",
        "properties": {
            "a": {
                "type": "number",
            },
            "b": {
                "type": "number",
            },
        },
        "required": ["a", "b"],
    },
    handler=calculator,
)


def square(x: float) -> float:
    return x * x


def add(a: float, b: float) -> float:
    return a + b


square_tool = Tool(
    name="square",
    description="Square a number.",
    parameters={
        "type": "object",
        "properties": {
            "x": {
                "type": "number",
            },
        },
        "required": ["x"],
    },
    handler=square,
)

add_tool = Tool(
    name="add",
    description="Add two numbers.",
    parameters={
        "type": "object",
        "properties": {
            "a": {
                "type": "number",
            },
            "b": {
                "type": "number",
            },
        },
        "required": ["a", "b"],
    },
    handler=add,
)

registry = ToolRegistry([calculator_tool, square_tool, add_tool])

model = OpenAICompatibleModel(
    endpoint=url,
    api_key=key,
    model="你的模型名",
)


def build_messages(state: AgentState) -> list[dict]:
    messages = [
        {
            "role": "user",
            "content": state.task,
        }
    ]

    for step in state.history:
        call = step.action
        observation = step.observation

        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                ],
            }
        )

        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": observation.result,
            }
        )

    return messages


state = AgentState(task="必须使用 calculator 工具计算 1234567 * 891011")


class AgentLoop:
    def __init__(
        self,
        model: OpenAICompatibleModel,
        tools: ToolRegistry,
        max_steps: int = 10,
    ) -> None:
        self.model = model
        self.tools = tools
        self.max_steps = max_steps

    def run(self, task: str) -> str:
        state = AgentState(task=task)

        for step_idx in range(self.max_steps):
            messages = build_messages(state)

            print(f"\n===== STEP {step_idx} =====")
            print(json.dumps(messages, indent=2, ensure_ascii=False))

            response = self.model.generate(
                messages=messages,
                tools=self.tools.schemas(),
            )

            print("MODEL RESPONSE:")
            print(response)

            if not response.tool_calls:
                return response.content or ""

            for call in response.tool_calls:
                result = self.tools.execute(
                    call.name,
                    call.arguments,
                )

                observation = Observation(
                    tool_call_id=call.id,
                    tool_name=call.name,
                    result=result,
                )

                state.history.append(
                    Step(
                        action=call,
                        observation=observation,
                    )
                )

                print("TOOL CALL:")
                print(call)

                print("OBSERVATION:")
                print(observation)

        raise RuntimeError(f"Agent exceeded max_steps={self.max_steps}")


agent = AgentLoop(
    model=model,
    tools=registry,
    max_steps=5,
)

answer = agent.run("""必须使用工具完成:
先计算 1234 的平方，
再给结果加上 5678。
不要自己心算。""")

print("\nFINAL ANSWER:")
print(answer)
