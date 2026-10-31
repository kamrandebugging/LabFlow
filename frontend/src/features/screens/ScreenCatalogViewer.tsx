import { useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { ALL_SCREENS, ScreenMeta } from "../../data/screensManifest";
import {
  ExternalLink,
  Search,
  Split,
  Eye,
  Image as ImageIcon,
  ChevronLeft,
  ChevronRight,
  Shield,
  Smartphone,
  CheckCircle2,
  ArrowLeft,
} from "lucide-react";

export function ScreenCatalogViewer(): JSX.Element {
  const { screenId } = useParams<{ screenId?: string }>();
  const navigate = useNavigate();

  const initialId = screenId ? parseInt(screenId, 10) : 1;
  const validInitialId =
    isNaN(initialId) || initialId < 1 || initialId > 43 ? 1 : initialId;

  const [selectedId, setSelectedId] = useState<number>(validInitialId);
  const [viewMode, setViewMode] = useState<"html" | "png" | "split">("html");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [filterBatch, setFilterBatch] = useState<number | "all">("all");

  const currentScreen: ScreenMeta =
    ALL_SCREENS.find((s) => s.id === selectedId) ?? ALL_SCREENS[0]!;

  const filteredScreens = ALL_SCREENS.filter((s) => {
    const matchesSearch =
      s.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.id.toString().includes(searchQuery) ||
      s.route.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesBatch = filterBatch === "all" || s.batch === filterBatch;
    return matchesSearch && matchesBatch;
  });

  const handleSelectScreen = (id: number) => {
    setSelectedId(id);
    navigate(`/screens/${id}`);
  };

  const handlePrev = () => {
    if (selectedId > 1) {
      handleSelectScreen(selectedId - 1);
    }
  };

  const handleNext = () => {
    if (selectedId < 43) {
      handleSelectScreen(selectedId + 1);
    }
  };

  const isInteractiveReact = currentScreen.id === 1 || currentScreen.id === 2;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Header */}
      <header className="bg-slate-900 border-b border-slate-800 px-4 py-2.5 flex items-center justify-between sticky top-0 z-40">
        <div className="flex items-center gap-3">
          <Link
            to="/login"
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white px-2.5 py-1.5 rounded bg-slate-800/80 hover:bg-slate-700 transition"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to App
          </Link>
          <div className="h-4 w-px bg-slate-700" />
          <div className="flex items-center gap-2">
            <span className="font-bold text-sm tracking-tight text-white flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              LabFlow Spec Master Catalog
            </span>
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-teal-900/60 border border-teal-700/50 text-teal-300 font-medium">
              43 / 43 Verified Screens
            </span>
          </div>
        </div>

        {/* Center: Screen Title & Navigation */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handlePrev}
            disabled={selectedId <= 1}
            aria-label="Previous screen"
            className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white disabled:opacity-30 disabled:pointer-events-none transition"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs font-semibold px-2 py-1 rounded bg-slate-800 border border-slate-700 text-slate-200">
            Screen {String(currentScreen.id).padStart(2, "0")}:{" "}
            {currentScreen.title.split(" - ")[0]}
          </span>
          <button
            type="button"
            onClick={handleNext}
            disabled={selectedId >= 43}
            aria-label="Next screen"
            className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white disabled:opacity-30 disabled:pointer-events-none transition"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        {/* Right: View Mode Controls & Direct Links */}
        <div className="flex items-center gap-2">
          {/* React interactive direct link */}
          {isInteractiveReact && (
            <Link
              to={currentScreen.id === 1 ? "/login" : "/login/2fa"}
              className="flex items-center gap-1 text-xs px-2.5 py-1 rounded bg-teal-600 hover:bg-teal-500 text-white font-medium transition"
            >
              {currentScreen.id === 1 ? (
                <Shield className="w-3.5 h-3.5" />
              ) : (
                <Smartphone className="w-3.5 h-3.5" />
              )}
              Live React Component
            </Link>
          )}

          {/* View Mode Toggle */}
          <div className="bg-slate-800/90 rounded-lg p-0.5 border border-slate-700 flex items-center gap-0.5 text-xs">
            <button
              type="button"
              onClick={() => setViewMode("html")}
              className={`px-2.5 py-1 rounded flex items-center gap-1 transition ${
                viewMode === "html"
                  ? "bg-teal-700 text-white font-medium"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
              HTML Live
            </button>
            <button
              type="button"
              onClick={() => setViewMode("split")}
              className={`px-2.5 py-1 rounded flex items-center gap-1 transition ${
                viewMode === "split"
                  ? "bg-teal-700 text-white font-medium"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Split className="w-3.5 h-3.5" />
              Split Spec
            </button>
            <button
              type="button"
              onClick={() => setViewMode("png")}
              className={`px-2.5 py-1 rounded flex items-center gap-1 transition ${
                viewMode === "png"
                  ? "bg-teal-700 text-white font-medium"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <ImageIcon className="w-3.5 h-3.5" />
              PNG Spec
            </button>
          </div>

          <a
            href={`/screens/${currentScreen.htmlFile}`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition"
            title="Open pure HTML in new tab"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Full Tab
          </a>
        </div>
      </header>

      {/* Main Workspace */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar: Screen Directory */}
        <aside className="w-80 bg-slate-900/95 border-r border-slate-800 flex flex-col flex-shrink-0">
          <div className="p-3 border-b border-slate-800 space-y-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
              <input
                type="text"
                placeholder="Search screen or route..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 rounded bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-teal-500"
              />
            </div>
            <div className="flex items-center gap-1 overflow-x-auto pb-1 text-[11px]">
              <button
                type="button"
                onClick={() => setFilterBatch("all")}
                className={`px-2 py-0.5 rounded-full whitespace-nowrap transition ${
                  filterBatch === "all"
                    ? "bg-teal-700 text-white font-semibold"
                    : "bg-slate-800 text-slate-400 hover:text-slate-200"
                }`}
              >
                All (43)
              </button>
              {[1, 2, 3, 4, 5].map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => setFilterBatch(b)}
                  className={`px-2 py-0.5 rounded-full whitespace-nowrap transition ${
                    filterBatch === b
                      ? "bg-teal-700 text-white font-semibold"
                      : "bg-slate-800 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Batch {b}
                </button>
              ))}
            </div>
          </div>

          {/* List of screens */}
          <div className="flex-1 overflow-y-auto divide-y divide-slate-800/50 p-2 space-y-1">
            {filteredScreens.map((s) => {
              const isSelected = s.id === currentScreen.id;
              const hasReact = s.id === 1 || s.id === 2;

              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => handleSelectScreen(s.id)}
                  className={`w-full text-left p-2.5 rounded-lg transition-all flex items-start gap-2.5 ${
                    isSelected
                      ? "bg-teal-950/80 border border-teal-600/60 shadow-sm"
                      : "hover:bg-slate-800/60 border border-transparent"
                  }`}
                >
                  <span
                    className={`font-mono text-[11px] font-bold px-1.5 py-0.5 rounded ${
                      isSelected
                        ? "bg-teal-600 text-white"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {String(s.id).padStart(2, "0")}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-xs font-medium text-slate-200 truncate">
                        {s.title.split(" - ")[0]}
                      </span>
                      {hasReact && (
                        <span className="text-[10px] uppercase font-bold text-teal-400 bg-teal-900/60 px-1 rounded flex-shrink-0">
                          React
                        </span>
                      )}
                    </div>
                    <div className="flex items-center justify-between gap-1 mt-0.5 text-[11px] text-slate-500">
                      <span className="truncate">{s.route}</span>
                      <span className="text-[10px] text-slate-600 flex-shrink-0">
                        B{s.batch}
                      </span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        {/* Content Viewer */}
        <main className="flex-1 flex flex-col bg-slate-900/50 overflow-hidden">
          {/* Screen Metadata sub-bar */}
          <div className="px-4 py-2 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center gap-3">
              <span className="text-white font-medium">
                {currentScreen.title}
              </span>
              <span className="text-slate-600">|</span>
              <span className="font-mono text-teal-400">
                Route: {currentScreen.route}
              </span>
              <span className="text-slate-600">|</span>
              <span className="text-slate-400">{currentScreen.batchName}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-emerald-400 bg-emerald-950/80 border border-emerald-800/60 px-2 py-0.5 rounded flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                Verified Spec (43 Screens Pack)
              </span>
            </div>
          </div>

          {/* Viewport Frame */}
          <div className="flex-1 relative overflow-hidden bg-slate-950">
            {viewMode === "html" && (
              <iframe
                title={currentScreen.title}
                src={`/screens/${currentScreen.htmlFile}`}
                className="w-full h-full border-0 bg-white"
              />
            )}

            {viewMode === "png" && (
              <div className="w-full h-full overflow-auto flex items-start justify-center p-6 bg-slate-950">
                <div className="max-w-5xl w-full bg-white rounded-lg shadow-2xl overflow-hidden border border-slate-800">
                  <div className="bg-slate-900 text-slate-400 px-4 py-1.5 text-xs font-mono border-b border-slate-800 flex items-center justify-between">
                    <span>Reference Spec PNG: {currentScreen.pngFile}</span>
                    <a
                      href={`/screens-png/${currentScreen.pngFile}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-teal-400 hover:underline flex items-center gap-1"
                    >
                      Open Raw PNG <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                  <img
                    src={`/screens-png/${currentScreen.pngFile}`}
                    alt={`Reference for ${currentScreen.title}`}
                    className="w-full h-auto block"
                  />
                </div>
              </div>
            )}

            {viewMode === "split" && (
              <div className="w-full h-full flex divide-x divide-slate-800">
                {/* Left pane: Live HTML */}
                <div className="w-1/2 h-full flex flex-col">
                  <div className="px-3 py-1.5 bg-slate-900 border-b border-slate-800 text-[11px] font-semibold text-teal-400 flex items-center justify-between">
                    <span className="flex items-center gap-1">
                      <Eye className="w-3.5 h-3.5" />
                      Live Rendered HTML (/screens/{currentScreen.htmlFile})
                    </span>
                    <a
                      href={`/screens/${currentScreen.htmlFile}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-slate-400 hover:text-white"
                    >
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                  <iframe
                    title={`${currentScreen.title} (Live HTML)`}
                    src={`/screens/${currentScreen.htmlFile}`}
                    className="flex-1 w-full border-0 bg-white"
                  />
                </div>

                {/* Right pane: PNG Spec Reference */}
                <div className="w-1/2 h-full flex flex-col bg-slate-950 overflow-hidden">
                  <div className="px-3 py-1.5 bg-slate-900 border-b border-slate-800 text-[11px] font-semibold text-teal-400 flex items-center justify-between">
                    <span className="flex items-center gap-1">
                      <ImageIcon className="w-3.5 h-3.5" />
                      Visual Reference Spec PNG (/screens-png/
                      {currentScreen.pngFile})
                    </span>
                    <a
                      href={`/screens-png/${currentScreen.pngFile}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-slate-400 hover:text-white"
                    >
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                  <div className="flex-1 overflow-auto p-4 flex items-start justify-center">
                    <img
                      src={`/screens-png/${currentScreen.pngFile}`}
                      alt={`Reference for ${currentScreen.title}`}
                      className="max-w-full h-auto rounded shadow border border-slate-800"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
