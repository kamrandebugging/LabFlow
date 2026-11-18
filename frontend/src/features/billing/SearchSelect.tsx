import { useMemo, useRef, useState } from "react";
import { Check } from "lucide-react";

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
  /** Single-select mode: called with the chosen option id. */
  onSelect?: (id: string) => void;
  /** Multi-select mode: clicking an option toggles it instead of choosing. */
  multiple?: boolean;
  /** Multi-select mode: ids that are currently selected (highlighted). */
  selectedIds?: string[];
  /** Multi-select mode: called when a row is toggled. */
  onToggle?: (id: string) => void;
  className?: string;
  inputClassName?: string;
  /** Optional id so an external <label htmlFor> can target the input. */
  inputId?: string;
}

/**
 * Searchable picker: type to filter, click (or Enter) to choose. Used for the
 * invoice test and panel pickers so a 100+ item catalogue is navigable.
 *
 * With `multiple`, rows toggle on click and stay highlighted (teal fill + tick)
 * so the user can pick several tests and add them in one action; the list stays
 * open until the user clicks away or presses Escape.
 */
export function SearchSelect({
  options,
  placeholder,
  ariaLabel,
  disabled,
  onSelect,
  multiple = false,
  selectedIds,
  onToggle,
  className,
  inputClassName,
  inputId,
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

  const chosen = (id: string) => (selectedIds ?? []).includes(id);

  const activate = (id: string) => {
    if (multiple) {
      onToggle?.(id);
      return;
    }
    onSelect?.(id);
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
        id={inputId}
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
            if (pick) activate(pick.id);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />

      {open && matches.length > 0 ? (
        <ul
          id="search-select-list"
          role="listbox"
          aria-multiselectable={multiple || undefined}
          style={{
            position: "absolute",
            zIndex: 40,
            insetInlineStart: 0,
            insetInlineEnd: "auto",
            /* Wide enough for "Test name (CODE) … PKR 0000.00" on one line:
               the panel is anchored to the input but grows past it. */
            minWidth: "100%",
            width: "max-content",
            maxWidth: "min(560px, 92vw)",
            top: "calc(100% + 4px)",
            maxHeight: 320,
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
          {matches.map((option, index) => {
            const isSelected = multiple
              ? chosen(option.id)
              : index === highlight;
            const isHighlighted = index === highlight;
            return (
              <li key={option.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={multiple ? chosen(option.id) : isHighlighted}
                  data-selected={isSelected ? "true" : undefined}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setHighlight(index)}
                  onClick={() => activate(option.id)}
                  style={{
                    display: "flex",
                    width: "100%",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                    padding: "7px 10px",
                    border: 0,
                    borderRadius: 8,
                    background: isSelected
                      ? "var(--color-accent)"
                      : isHighlighted
                        ? "var(--veyla-well)"
                        : "transparent",
                    color: isSelected
                      ? "var(--color-accent-text)"
                      : "var(--color-text)",
                    fontSize: 12,
                    fontWeight: 600,
                    textAlign: "start",
                    cursor: "pointer",
                  }}
                >
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      minWidth: 0,
                    }}
                  >
                    {multiple ? (
                      <Check
                        size={13}
                        aria-hidden="true"
                        style={{
                          visibility: isSelected ? "visible" : "hidden",
                          flexShrink: 0,
                        }}
                      />
                    ) : null}
                    <span
                      style={{
                        minWidth: 0,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {option.label}
                    </span>
                  </span>
                  {option.meta ? (
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        color: isSelected
                          ? "var(--color-accent-text)"
                          : "var(--color-text-muted)",
                        whiteSpace: "nowrap",
                        flexShrink: 0,
                      }}
                    >
                      {option.meta}
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

export default SearchSelect;
