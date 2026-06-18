import { ArrowUp, Loader } from "lucide-react";
import { useState } from "react";
const API_BASE = "http://localhost:8000";

const MessageSection = () => {
  const [serverOk, setServerOk] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Array<{ id: number; role: "user" | "assistant"; text: string }>>([]);

  async function handleSendQuery() {
    if (!query.trim()) return;

    const userMsg = { id: Date.now(), role: "user" as const, text: query };
 
    setMessages((m) => [...m, userMsg]);
    setQuery("");
    setLoading(true);

    // insert assistant skeleton
    const placeholderId = Date.now() + 1;
    const placeholder = { id: placeholderId, role: "assistant" as const, text: "..." };
    setMessages((m) => [...m, placeholder]);

    try {
      const res = await fetch(`${API_BASE}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: userMsg.text }),
      }).then((r) => r.json());
      setServerOk(res?.status === "ok");

      const assistantText = res?.answer ?? res?.text ?? "(no response)";
      // replace placeholder with actual assistant response
      setMessages((m) => m.map((msg) => (msg.id === placeholderId ? { ...msg, text: assistantText } : msg)));
    } catch (e) {
      setServerOk(false);
      const errText = "Error contacting server";
      setMessages((m) => m.map((msg) => (msg.id === placeholderId ? { ...msg, text: errText } : msg)));
    }
    finally {
      setLoading(false);
    }
  }
  return (
    <section className="flex justify-center mt-8 ">
      {/* Phone */}
      <div className="rounded-xl flex flex-col relative  w-100 h-150 border border-black/50">
        <div className=" flex items-center gap-2 border-b border-black/25 justify-center h-12 w-full">
          <p className="text-center text-base">Memoria</p>
          <div
            className={`w-2 h-2 rounded-full ${serverOk ? "bg-green-500" : "bg-red-500"}`}
          ></div>
        </div>

        {/* Message Content */}

        <div className="overflow-y-auto scrollbar-thin p-4  flex-1 flex-col flex bg-gray-200">
          {messages.map((m) => (
            <div key={m.id} className={`mb-2 w-fit max-w-2/3 rounded ${m.role === "user" ? "text-right self-end bg-green-300" : "text-left bg-white"}`}>
              <div className="inline-block p-2  ">{m.text}</div>
            </div>
          ))}
        </div>

        <div className=" flex gap-2 w-full p-2">
          <input
            type="text"
            className="flex-1"
            name="query"
            id="query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSendQuery(); }}
            disabled={loading}
          />
          <button
            onClick={handleSendQuery}
            className="px-4 py-2 rounded-2xl bg-green-800 text-white"
            disabled={loading}
          >
            {loading ? <Loader className="animate-spin" /> : <ArrowUp />}
          </button>
        </div>
      </div>
    </section>
  );
};

export default MessageSection;
