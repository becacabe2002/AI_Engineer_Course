# Assignment 3: Multi-Agent Painter & Critic

## Overview
This project implements a multi-agent system using the AG2 framework where two agents collaborate iteratively to produce a digital drawing. A **Painter** agent draws on a digital canvas using tools, and a **Critic** agent visually evaluates the drawing and provides feedback.

## How to Run
Assuming you are in the root directory of the repository:

1. Download the required packages using `uv`:
   ```bash
   uv sync
   ```
2. Run the main script:
   ```bash
   uv run ./assignment-3-multiagent/main.py
   ```
3. The script will prompt you for two inputs:
   - **Number of drawing loops (rounds):** (Enter at least 10 as per assignment requirements).
   - **Subject prompt:** Enter the desired subject for the Painter.
     > ⚠️ **IMPORTANT NOTICE:** You should include `"within 200x200 size canvas"` in your prompt so that the agent won't draw outside of the predefined canvas size. Example: *"Draw a dog standing on the grass within 200x200 size canvas"*.
4. The system will run the multi-agent loop. After each round, it will save the intermediate canvas state as an image file (e.g., `round_01.png`, `round_02.png`).
5. Upon completion, a full transcript of the interaction will be saved to `conversation_log.txt`.

## Drawing Subject
The script allows the user to input any subject prompt at runtime. A good example to test the system's capabilities is:
> "Draw a landscape with a green grassy field at the bottom, a brown tree trunk with green leaves, and a bright yellow sun in the sky within 200x200 size canvas."

## Design Decisions

### Orchestration Pattern
We implemented a **Group Chat with a Custom Deterministic State Machine** using an Actor-Executor-Critic loop.
- **Why?** Relying on the LLM for speaker selection (auto mode) can lead to unpredictable conversation flows where agents talk over each other or skip the execution step. The custom `custom_speaker_selector` strictly enforces the sequence: **Painter** (Actor) -> **Executor** (Tool execution & Image save) -> **Critic** (Evaluation) -> **Painter** (Next iteration). This ensures reliable, round-based progress.

### Tools Provided
The Painter is equipped with high-level shape drawing tools: `draw_rectangle`, `draw_circle`, `draw_line`, `draw_triangle`, and `draw_square`.
- **Why?** As noted in the assignment, drawing single pixels results in negligible progress per round and consumes too many tokens. Providing shape-drawing tools allows the Painter to make substantial, visible additions to the canvas in a single turn, enabling the Critic to provide meaningful feedback immediately.

### Multimodal Vision Context
We utilized AG2's `register_hook` mechanism (`process_all_messages_before_reply`) to dynamically append a base64-encoded image of the current `DigitalCanvas` to the message history before the Painter or Critic replies.
- **Why?** This ensures that both the Critic (when evaluating) and the Painter (when drawing) always "see" the live, up-to-date visual state of the canvas without requiring manual image file passing in the main loop.

## Observations on Output Images

### What went well
- **Iterative Improvement:** The system successfully demonstrates iterative refinement. The Critic reliably identifies missing elements from the prompt, and the Painter actively incorporates this feedback in the next round by calling the appropriate tools.
- **Tool Adherence:** The Painter agent adheres well to the strict system prompt, expressing its actions exclusively through tool calls rather than conversational text.

### What went wrong (Limitations)
- **Spatial Reasoning:** While the LLMs can "see" the image, they often struggle with precise 2D coordinate math. This can result in misaligned shapes (e.g., a roof floating above a house instead of sitting on it) or incorrect scaling.
- **Over-correction:** Sometimes the Critic's feedback can be overly aggressive, causing the Painter to draw over existing correct shapes rather than adding to empty space, leading to a cluttered canvas in later rounds.