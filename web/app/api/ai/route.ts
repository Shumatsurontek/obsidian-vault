import { streamText, convertToModelMessages } from "ai";

// Chat route streamed via the Vercel AI Gateway.
export const maxDuration = 300;

export async function POST(req: Request) {
  const { messages } = await req.json();

  const result = streamText({
    model: process.env.AI_GATEWAY_MODEL ?? "anthropic/claude-opus-4-7",
    system:
      "You assist with an Obsidian vault. For destructive or organizational " +
      "operations, suggest invoking the /api/chat backend (Deep Agents organizer). " +
      "For quick Q&A, answer directly.",
    messages: convertToModelMessages(messages),
  });

  return result.toTextStreamResponse();
}
