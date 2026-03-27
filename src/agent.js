import { callLLM } from "./llm.js";
import { TOOL_DEFINITIONS, executeTool } from "./tools.js";
import { buildSystemPrompt } from "./prompt.js";
import { log, stopSpinner } from "./logger.js";
import chalk from "chalk";

const MAX_TOOL_CALLS = 40;
const MAX_TEXT_ONLY_RESPONSES = 3;

export async function runAgent(projectDir, repoUrl, repoMeta, pythonInfo) {
  const systemPrompt = buildSystemPrompt(projectDir, repoMeta, pythonInfo);

  const messages = [
    { role: "system", content: systemPrompt },
    {
      role: "user",
      content: `Install this repository: ${repoUrl}\nThe code has been downloaded to: ${projectDir}\nAnalyze the project and install all dependencies so it can be run.`,
    },
  ];

  // Stop the spinner before the agent loop — per-line tool output conflicts
  // with ora's ANSI cursor rewrites, causing previous lines to disappear.
  stopSpinner();

  let toolCallCount = 0;
  let finished = false;
  let textOnlyCount = 0;
  let finalResult = { success: false, summary: "Installation did not complete." };

  while (!finished && toolCallCount < MAX_TOOL_CALLS) {
    let assistantMessage;
    try {
      assistantMessage = await callLLM(messages, TOOL_DEFINITIONS);
    } catch (err) {
      log(chalk.red(`LLM API error: ${err.message}`));
      finalResult.summary = `LLM API error: ${err.message}`;
      break;
    }

    // Push the full assistant message (critical for API format)
    messages.push(assistantMessage);

    // If the LLM responded with text only (no tool calls)
    if (
      !assistantMessage.tool_calls ||
      assistantMessage.tool_calls.length === 0
    ) {
      textOnlyCount++;
      if (assistantMessage.content) {
        log(chalk.gray(`  LLM: ${assistantMessage.content.slice(0, 200)}`));
      }

      if (textOnlyCount >= MAX_TEXT_ONLY_RESPONSES) {
        log(chalk.yellow("LLM stopped calling tools. Forcing finish."));
        finalResult.summary =
          "LLM stopped calling tools before completing installation.";
        break;
      }

      messages.push({
        role: "user",
        content:
          "Continue with the installation. Use the available tools to proceed. Remember to call finish() when done.",
      });
      continue;
    }

    // Reset text-only counter on tool use
    textOnlyCount = 0;

    // Execute each tool call sequentially
    for (const toolCall of assistantMessage.tool_calls) {
      toolCallCount++;
      log(
        chalk.gray(
          `  [${toolCallCount}/${MAX_TOOL_CALLS}] ${toolCall.function.name}(${toolCall.function.arguments.slice(0, 80)})`
        )
      );

      if (toolCallCount > MAX_TOOL_CALLS) {
        messages.push({
          role: "tool",
          tool_call_id: toolCall.id,
          content:
            "MAX TOOL CALLS REACHED (40). You must call finish() now or installation will be terminated.",
        });
        break;
      }

      const result = await executeTool(toolCall, projectDir);

      // Check if this was a finish call
      if (toolCall.function.name === "finish") {
        try {
          const parsed = JSON.parse(result);
          if (parsed.__finish) {
            finished = true;
            finalResult = {
              success: parsed.success,
              summary: parsed.summary,
            };
          }
        } catch {
          // finish returned non-JSON, treat as finished
          finished = true;
          finalResult = { success: true, summary: result };
        }
      }

      messages.push({
        role: "tool",
        tool_call_id: toolCall.id,
        content: result,
      });

      if (finished) break;
    }
  }

  // If we hit the tool call limit without finishing
  if (!finished && toolCallCount >= MAX_TOOL_CALLS) {
    log(chalk.yellow("Reached maximum tool call limit (40)."));
    // Give the LLM one last chance to call finish
    messages.push({
      role: "user",
      content:
        "You have reached the tool call limit. Please call finish() immediately with a summary of what was accomplished.",
    });

    try {
      const lastMessage = await callLLM(messages, TOOL_DEFINITIONS);
      messages.push(lastMessage);

      if (lastMessage.tool_calls) {
        for (const tc of lastMessage.tool_calls) {
          if (tc.function.name === "finish") {
            const result = await executeTool(tc, projectDir);
            try {
              const parsed = JSON.parse(result);
              if (parsed.__finish) {
                finalResult = {
                  success: parsed.success,
                  summary: parsed.summary,
                };
              }
            } catch {
              finalResult = { success: false, summary: result };
            }
          }
        }
      }
    } catch {
      // Last chance failed, use whatever we have
    }
  }

  return finalResult;
}
