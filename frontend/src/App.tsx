import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Database,
  FileText,
  RefreshCw,
  Search,
  Shield,
  Tag,
  Trash2,
  Upload,
} from "lucide-react";
import { ArrowUp } from "lucide-react";
import MessageSection from "./MessageSection";
const API_BASE = "http://localhost:8000";

type DocumentItem = {
  id: string;
  title: string | null;
  source_system: string;
  source_id: string | null;
  source_type: string;
  tags: string[];
  metadata: Record<string, unknown>;
  chunk_count: number;
  ingested_at: string | null;
};

type SearchHit = {
  chunk_id: string;
  document_id: string;
  title: string | null;
  content: string;
  score: number;
  source_system: string;
  source_id: string | null;
  tags: string[];
  metadata: Record<string, unknown>;
};

type SearchResponse = {
  query: string;
  answer: string | null;
  hits: SearchHit[];
  permission_notice: string;
};

type Health = {
  status: string;
  database: string;
  embedding_model: string;
  embedding_dimension: number;
};

const emptyIngest = {
  title: "",
  sourceId: "",
  sourceType: "document",
  tags: "circle:my_family:demo-profile, profile:demo-profile",
  text: "",
};

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [ingest, setIngest] = useState(emptyIngest);
  const [query, setQuery] = useState("family memories");
  const [tagFilters, setTagFilters] = useState("");
  const [topK, setTopK] = useState(5);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const totalChunks = useMemo(
    () => documents.reduce((total, item) => total + item.chunk_count, 0),
    [documents],
  );

  useEffect(() => {
    void refreshAll();
  }, []);

  async function refreshAll() {
    await Promise.all([loadHealth(), loadDocuments()]);
  }

  async function loadHealth() {
    try {
      const response = await fetch(`${API_BASE}/health`);
      setHealth(await response.json());
    } catch {
      setHealth(null);
    }
  }

  async function loadDocuments() {
    try {
      const response = await fetch(`${API_BASE}/api/documents`);
      if (response.ok) {
        setDocuments(await response.json());
      }
    } catch {
      setDocuments([]);
    }
  }

  async function handleIngest(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/documents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: ingest.title || null,
          text: ingest.text,
          source_system: "manual",
          source_id: ingest.sourceId || null,
          source_type: ingest.sourceType || "document",
          tags: splitCsv(ingest.tags),
          metadata: { entered_from: "rag_console" },
        }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }
      setIngest({ ...emptyIngest, text: "" });
      setMessage("Document ingested.");
      await loadDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Ingest failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/rag/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          top_k: topK,
          tag_filters: splitCsv(tagFilters),
          include_answer: true,
        }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }
      setSearchResult(await response.json());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Search failed.");
    } finally {
      setBusy(false);
    }
  }

  async function removeDocument(id: string) {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/documents/${id}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      await loadDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Delete failed.");
    } finally {
      setBusy(false);
    }
  }

 

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Aternum RAG Sandbox</p>
          <h1>Retrieval Console</h1>
        </div>
        <button
          className="iconButton"
          title="Refresh"
          onClick={() => void refreshAll()}
        >
          <RefreshCw size={18} />
        </button>
      </header>

      <section className="statusGrid" aria-label="Service status">
        <Metric
          icon={<Database size={18} />}
          label="Database"
          value={health?.database ?? "offline"}
        />
        <Metric
          icon={<FileText size={18} />}
          label="Documents"
          value={String(documents.length)}
        />
        <Metric
          icon={<Tag size={18} />}
          label="Chunks"
          value={String(totalChunks)}
        />
        <Metric icon={<Shield size={18} />} label="Permissions" value="TODO" />
      </section>

      {message && <div className="notice">{message}</div>}

      <section className="workspace">
        <form className="panel searchPanel" onSubmit={handleSearch}>
          <div className="panelHeader">
            <Search size={18} />
            <h2>Search</h2>
          </div>
          <label>
            Query
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              rows={4}
              required
            />
          </label>
          <div className="inlineFields">
            <label>
              Top K
              <input
                type="number"
                min={1}
                max={25}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
              />
            </label>
            <label>
              Tag filters
              <input
                value={tagFilters}
                onChange={(event) => setTagFilters(event.target.value)}
                placeholder="circle:my_family:..."
              />
            </label>
          </div>
          <button className="primaryButton" disabled={busy}>
            <Search size={17} />
            Run Search
          </button>
        </form>

        <form className="panel ingestPanel" onSubmit={handleIngest}>
          <div className="panelHeader">
            <Upload size={18} />
            <h2>Ingest</h2>
          </div>
          <div className="inlineFields">
            <label>
              Title
              <input
                value={ingest.title}
                onChange={(event) =>
                  setIngest({ ...ingest, title: event.target.value })
                }
              />
            </label>
            <label>
              Source ID
              <input
                value={ingest.sourceId}
                onChange={(event) =>
                  setIngest({ ...ingest, sourceId: event.target.value })
                }
              />
            </label>
          </div>
          <label>
            Tags
            <input
              value={ingest.tags}
              onChange={(event) =>
                setIngest({ ...ingest, tags: event.target.value })
              }
            />
          </label>
          <label>
            Text
            <textarea
              value={ingest.text}
              onChange={(event) =>
                setIngest({ ...ingest, text: event.target.value })
              }
              rows={8}
              required
            />
          </label>
          <button className="primaryButton" disabled={busy}>
            <Upload size={17} />
            Ingest
          </button>
        </form>
      </section>

      {searchResult && (
        <section className="results">
          <div className="sectionHeader">
            <h2>Results</h2>
            <span>{searchResult.hits.length} hits</span>
          </div>
          <pre className="answer">{searchResult.answer}</pre>
          <div className="hitList">
            {searchResult.hits.map((hit) => (
              <article className="hit" key={hit.chunk_id}>
                <div className="hitHeader">
                  <strong>{hit.title || hit.source_id || "Untitled"}</strong>
                  <span>{hit.score.toFixed(3)}</span>
                </div>
                <p>{hit.content}</p>
                <TagList tags={hit.tags} />
              </article>
            ))}
          </div>
          <p className="permissionNote">{searchResult.permission_notice}</p>
        </section>
      )}

      <section className="documents">
        <div className="sectionHeader">
          <h2>Documents</h2>
          <span>{health?.embedding_model ?? "embedding model pending"}</span>
        </div>
        <div className="documentList">
          {documents.map((item) => (
            <article className="documentItem" key={item.id}>
              <div>
                <strong>{item.title || item.source_id || "Untitled"}</strong>
                <p>
                  {item.source_system} / {item.source_type} / {item.chunk_count}{" "}
                  chunks
                </p>
                <TagList tags={item.tags} />
              </div>
              <button
                className="iconButton danger"
                title="Delete"
                onClick={() => void removeDocument(item.id)}
              >
                <Trash2 size={17} />
              </button>
            </article>
          ))}
        </div>
      </section>

      <MessageSection  />
    </main>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: JSX.Element;
  label: string;
  value: string;
}) {
  return (
    <div className="metric">
      {icon}
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function TagList({ tags }: { tags: string[] }) {
  if (!tags.length) {
    return <div className="tags muted">No tags</div>;
  }
  return (
    <div className="tags">
      {tags.map((tag) => (
        <span key={tag}>{tag}</span>
      ))}
    </div>
  );
}

function splitCsv(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export default App;
