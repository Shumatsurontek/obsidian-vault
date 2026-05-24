"use client";

import { useState } from "react";

type Msg = { role: "user" | "assistant"; content: string };

export default function Home() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [organizerStatus, setOrganizerStatus] = useState<string | null>(null);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    const next: Msg[] = [...messages, { role: "user", content: input }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      const res = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: next }),
      });
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let acc = "";
      setMessages((m) => [...m, { role: "assistant", content: "" }]);
      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          acc += decoder.decode(value, { stream: true });
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { role: "assistant", content: acc };
            return copy;
          });
        }
      }
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", content: `error: ${String(err)}` }]);
    } finally {
      setBusy(false);
    }
  };

  const runOrganizerPass = async () => {
    setOrganizerStatus("running...");
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: null }),
      });
      const data = await res.json();
      setOrganizerStatus(data.response?.slice(0, 800) ?? JSON.stringify(data));
    } catch (err) {
      setOrganizerStatus(`error: ${String(err)}`);
    }
  };

  return (
    <main style={{ maxWidth: 820, margin: "40px auto", padding: 24 }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>vault-mcp</h1>
        <p style={{ margin: "4px 0 0", color: "#888" }}>
          Proactive Obsidian vault organizer · Deep Agents · AI Gateway
        </p>
      </header>

      <section style={{ border: "1px solid #222", borderRadius: 8, padding: 16, marginBottom: 24 }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>Organizer</h2>
        <button
          onClick={runOrganizerPass}
          style={{ background: "#1a73e8", color: "white", border: 0, padding: "8px 14px", borderRadius: 6, cursor: "pointer" }}
        >
          Run one pass now
        </button>
        {organizerStatus && (
          <pre style={{ whiteSpace: "pre-wrap", marginTop: 12, color: "#aaa" }}>{organizerStatus}</pre>
        )}
      </section>

      <section style={{ border: "1px solid #222", borderRadius: 8, padding: 16 }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>Chat with the vault</h2>
        <div style={{ minHeight: 200, marginBottom: 12 }}>
          {messages.map((m, i) => (
            <div key={i} style={{ margin: "8px 0" }}>
              <strong style={{ color: m.role === "user" ? "#7cc4ff" : "#9be37c" }}>{m.role}:</strong>{" "}
              <span style={{ whiteSpace: "pre-wrap" }}>{m.content}</span>
            </div>
          ))}
        </div>
        <form onSubmit={send} style={{ display: "flex", gap: 8 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your vault..."
            style={{ flex: 1, padding: 8, background: "#15181b", color: "#e6e6e6", border: "1px solid #222", borderRadius: 6 }}
          />
          <button
            type="submit"
            disabled={busy}
            style={{ background: "#9be37c", color: "#0b0d10", border: 0, padding: "8px 14px", borderRadius: 6, cursor: "pointer" }}
          >
            Send
          </button>
        </form>
      </section>
    </main>
  );
}
