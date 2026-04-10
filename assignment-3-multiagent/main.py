import logging

import autogen

from canvas import DigitalCanvas


logging.basicConfig(level=logging.INFO)

# Use the OpenRouter proxy endpoint specified in the assignment.
llm_config = {
    "config_list": [
        {
            "model": "openai/gpt-4.1-mini",
            "api_key": "not-needed",
            "base_url": "https://5f5832nb90.execute-api.eu-central-1.amazonaws.com/v1",
        }
    ]
}


canvas = DigitalCanvas(200, 200)

painter = autogen.ConversableAgent(
    name="Painter",
    system_message=(
        "You are an AI Painter. You draw on a digital canvas based on the subject prompt and the Critic's feedback.\n"
        "You MUST use the drawing tools provided to you on EVERY turn to add or modify details on the canvas.\n"
        "Always draw multiple pixels/shapes at once instead of a single pixel.\n"
        "\n"
        "Conversation protocol (VERY IMPORTANT):\n"
        "- On each of your turns, you must ONLY call one or more drawing tools to update the canvas.\n"
        "- Do NOT send any text before or after tool calls.\n"
        "- Do NOT ask the Critic any questions.\n"
        "- Do NOT discuss coordinates or plans in text; express your changes only via tool calls.\n"
        "- Ignore any questions from the Critic. Instead, simply improve the drawing according to their latest feedback.\n"
        "- Never produce a reply that lacks tool calls. If you cannot think of improvements, still refine or slightly adjust the drawing using the tools.\n"
    ),
    llm_config=llm_config,
    human_input_mode="NEVER",
)

executor = autogen.ConversableAgent(
    name="Executor",
    system_message="An agent that executes drawing tools.",
    llm_config=False,
    human_input_mode="NEVER",
)


critic = autogen.ConversableAgent(
    name="Critic",
    system_message=(
        "You are an AI Art Critic. You visually evaluate the Painter's drawing.\n"
        "Provide structured, actionable feedback in THREE sections ONLY:\n"
        "1. What works well\n"
        "2. What should be changed\n"
        "3. Specific suggestions for the next iteration (including concrete coordinates, colors, and shapes).\n"
        "\n"
        "Conversation protocol (VERY IMPORTANT):\n"
        "- On each of your turns, you must output exactly these three sections of feedback, in text.\n"
        "- Do NOT ask the Painter any questions.\n"
        "- Do NOT invite further clarification. Assume the Painter will simply act on your feedback.\n"
        "- Do NOT use tools yourself. Only provide text feedback.\n"
        "- At the END of every message, append this exact instruction to the Painter:\n"
        "  'Now improve the drawing according to these suggestions, using the drawing tools.'\n"
        "\n"
        "IMPORTANT: Never include open-ended questions or options. Always give direct instructions and end with the fixed instruction above.\n"
    ),
    llm_config=llm_config,
    human_input_mode="NEVER",
)

# Register tools for executor agent
@painter.register_for_llm(name="draw_rectangle", description="Draw a filled rectangle")
@executor.register_for_execution(name="draw_rectangle")
def tool_draw_rectangle(x0: int, y0: int, x1: int, y1: int, color: str) -> str:
    return canvas.draw_rectangle(x0, y0, x1, y1, color)

@painter.register_for_llm(name="draw_circle", description="Draw a filled circle")
@executor.register_for_execution(name="draw_circle")
def tool_draw_circle(x: int, y: int, radius: int, color: str) -> str:
    return canvas.draw_circle(x, y, radius, color)

@painter.register_for_llm(name="draw_line", description="Draw a line")
@executor.register_for_execution(name="draw_line")
def tool_draw_line(x0: int, y0: int, x1: int, y1: int, width: int, color: str) -> str:
    return canvas.draw_line(x0, y0, x1, y1, width, color)

@painter.register_for_llm(name="draw_triangle", description="Draw a filled triangle by specifying 3 vertices")
@executor.register_for_execution(name="draw_triangle")
def tool_draw_triangle(x1: int, y1: int, x2: int, y2: int, x3: int, y3: int, color: str) -> str:
    return canvas.draw_triangle(x1, y1, x2, y2, x3, y3, color)

@painter.register_for_llm(name="draw_square", description="Draw a filled square centered at (x, y) with side length `size`")
@executor.register_for_execution(name="draw_square")
def tool_draw_square(x: int, y: int, size: int, color: str) -> str:
    return canvas.draw_square(x, y, size, color)

num_loops = int(input("Enter number of drawing loops (e.g., 5, 10): "))
MAX_ROUNDS = num_loops
round_counter = 1
last_saved_msg_index = 0


def append_canvas_to_messages(messages):
    """Append the current canvas image as a vision input to the last message.

    This hook is registered for both Painter and Critic so each agent "sees"
    the up-to-date canvas when generating a reply.
    """
    if not messages:
        return messages

    msgs = messages.copy()
    last_msg = msgs[-1].copy()
    msgs[-1] = last_msg

    # Only append if it's a standard text message (not a tool call)
    if last_msg.get("content") and "tool_calls" not in last_msg:
        img_b64 = canvas.get_base64()
        text_content = last_msg["content"]

        # Convert to multimodal list format expected by the OpenAI-compatible
        # vision API: a list of content parts including text and an image URL
        # with a base64-encoded PNG.
        if isinstance(text_content, str):
            last_msg["content"] = [
                {"type": "text", "text": text_content},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ]

    return msgs

# Register the hook for both agents so they can both see the canvas
painter.register_hook(hookable_method="process_all_messages_before_reply", hook=append_canvas_to_messages)
critic.register_hook(hookable_method="process_all_messages_before_reply", hook=append_canvas_to_messages)

def custom_speaker_selector(last_speaker: autogen.Agent, groupchat: autogen.GroupChat) -> autogen.Agent:
    global round_counter, last_saved_msg_index
    messages = groupchat.messages
    if not messages:
        return painter
    
    last_message = messages[-1]
    
    if last_speaker is critic:
        return painter
    elif last_speaker is painter:
        if "tool_calls" in last_message:
            return executor
        else:
            return critic
    elif last_speaker is executor:
        if len(messages) > last_saved_msg_index:
            filename = f"round_{round_counter:02d}.png"
            canvas.save(filename)
            print(f"Saved {filename}")
            round_counter += 1
            last_saved_msg_index = len(messages)
        return critic
        
    return painter

if __name__ == "__main__":
    subject_prompt = input("Enter the subject prompt (e.g., 'Draw a dog standing on the grass'): ")
    
    print(f"Starting Multi-Agent drawing process for subject: {subject_prompt}")
    
    groupchat = autogen.GroupChat(
        agents=[painter, critic, executor],
        messages=[],
        max_round=num_loops * 4,  # Sufficient rounds for the multi-step loops
        speaker_selection_method=custom_speaker_selector,
    )
    manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=llm_config)
    
    chat_result = critic.initiate_chat(
        manager,
        message=f"Let's start! Our subject is: '{subject_prompt}'. Please use your tools to draw the initial version.",
    )
    
    # Save the final conversation log
    with open("conversation_log.txt", "w", encoding="utf-8") as f:
        for msg in chat_result.chat_history:
            f.write(f"Role: {msg.get('role', 'N/A')}\n")
            f.write(f"Name: {msg.get('name', 'N/A')}\n")
            
            content = msg.get("content", "")
            if isinstance(content, list):
                # Filter out the huge base64 image strings from the log
                text_parts = [item['text'] for item in content if item['type'] == 'text']
                content = " ".join(text_parts) + " [IMAGE ATTACHED]"
                
            f.write(f"Content: {content}\n")
            if "tool_calls" in msg:
                f.write(f"Tool Calls: {msg['tool_calls']}\n")
            f.write("-" * 40 + "\n")
            
    print("Process complete. Conversation saved to conversation_log.txt")