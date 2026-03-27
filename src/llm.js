const API_URL = "https://openrouter.ai/api/v1/chat/completions";
const MODEL = "xiaomi/mimo-v2-flash";
const MAX_RETRIES = 3;
const RETRY_DELAYS = [1000, 2000, 4000];

export async function callLLM(messages, toolDefinitions) {
  const apiKey = process.env.OPENROUTER_API_KEY;

  const body = {
    model: MODEL,
    messages,
    tools: toolDefinitions,
    temperature: 0.2,
    max_tokens: 4096,
  };

  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (response.status === 429 || response.status >= 500) {
      if (attempt < MAX_RETRIES - 1) {
        await sleep(RETRY_DELAYS[attempt]);
        continue;
      }
      throw new Error(
        `OpenRouter API error: HTTP ${response.status} after ${MAX_RETRIES} retries`
      );
    }

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`OpenRouter API error: HTTP ${response.status} — ${text}`);
    }

    const data = await response.json();

    if (!data.choices || !data.choices[0] || !data.choices[0].message) {
      if (attempt < MAX_RETRIES - 1) {
        await sleep(RETRY_DELAYS[attempt]);
        continue;
      }
      throw new Error("OpenRouter API returned malformed response (no choices)");
    }

    return data.choices[0].message;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
