import { useMemo, useRef, useState } from "react";

export interface SearchOption {
  id: string;
  label: string;
  meta?: string;
}

interface SearchSelectProps {
  options: SearchOption[];
  placeholder: string;
  ariaLabel: string;
  disabled?: boolean;
  /** Called with the chosen option id. */
  onSelect: (id: string) => void;
  className?: string;
  inputClassName?: string;
}

/**
 * Searchable picker: type to filter, click (or Enter) to choose. Used for the
 * invoice test and panel pickers so a 100+ item catalogue is navigable.
 */
export function SearchSelect({
  options,
  placeholder,
  ariaLabel,
  disabled,
  onSelect,
  className,
  inputClassName,
}: SearchSelectProps): JSX.Element {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = q
      ? options.filter(
          (o) =>
            o.label.toLowerCase().includes(q) ||
            (o.meta || "").toLowerCase().includes(q),
        )
      : options;
    return rows.slice(0, 40);
  }, [options, query]);

  const choose = (id: string) => {
    onSelect(id);
    setQuery("");
    setOpen(false);
    setHighlight(0);
  };

  return (
    <div
      ref={wrapRef}
      className={className}
      style={{ position: "relative", minWidth: 0 }}
      onBlur={(e) => {
        if (!wrapRef.current?.contains(e.relatedTarget as Node)) {
          setOpen(false);
        }
      }}
    >
      <input
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls="search-select-list"
        aria-label={ariaLabel}
        placeholder={placeholder}
        value={query}
        disabled={disabled}
        className={inputClassName}
        autoComplete="off"
        style={{ width: "100%" }}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setHighlight(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
            setHighlight((h) => Math.min(h + 1, matches.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setHighlight((h) => Math.max(h - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            const pick = matches[highlight];
            if (pick) choose(pick.id);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />

      {open && matches.length > 0 ? (
        <ul
          id="search-select-list"
          role="listbox"
          style={{
            position: "absolute",
            zIndex: 40,
            insetInlineStart: 0,
            insetInlineEnd: 0,
            top: "calc(100% + 4px)",
            maxHeight: 260,
            overflowY: "auto",
            margin: 0,
            padding: 4,
            listStyle: "none",
            borderRadius: 12,
            border: "1px solid var(--color-border)",
            background: "var(--color-surface)",
            boxShadow: "var(--shadow-veyla-dropdown)",
          }}
        >
          {matches.map((option, index) => (
            <li key={option.id}>
              <button
                type="button"
                role="option"
                aria-selected={index === highlight}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setHighlight(index)}
                onClick={() => choose(option.id)}
                style={{
                  display: "flex",
                  width: "100%",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 10,
                  padding: "7px 10px",
                  border: 0,
                  borderRadius: 8,
                  background:
                    index === highlight ? "var(--veyla-well)" : "transparent",
                  color: "var(--color-text)",
                  fontSize: 12,
                  fontWeight: 600,
                  textAlign: "start",
                  cursor: "pointer",
                }}
              >
                <span style={{ minWidth: 0, overflow: "hidden" }}>
                  {option.label}
                </span>
                {option.meta ? (
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      color: "var(--color-text-muted)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {option.meta}
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default SearchSelect;
