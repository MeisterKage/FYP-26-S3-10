/**
 * The article body editor (PDD Figure 5.54: "a rich-text body with a basic
 * formatting toolbar").
 *
 * Built on contentEditable rather than a library. The toolbar is five buttons,
 * the output is the small HTML subset the server already allows, and pulling in
 * an editor framework would add far more than it earns here.
 *
 * Everything it produces is sanitised on write regardless. sanitize.py is the
 * authority on what survives, not this component: a writer can paste anything,
 * and the toolbar is a convenience rather than a control.
 */
import { useEffect, useRef } from "react";

const TOOLS = [
  { command: "bold", label: "Bold", glyph: "B", style: { fontWeight: 700 } },
  { command: "italic", label: "Italic", glyph: "I", style: { fontStyle: "italic" } },
  { command: "formatBlock", value: "h2", label: "Heading", glyph: "H" },
  { command: "insertUnorderedList", label: "Bulleted list", glyph: "•—" },
  { command: "createLink", label: "Link", glyph: "\u{1F517}" },
];

export default function RichText({ id, value, onChange, disabled, ...rest }) {
  const ref = useRef(null);

  // Write into the element only when the incoming value genuinely differs.
  // Assigning innerHTML on every render would move the caret to the start on
  // each keystroke, which makes the field unusable.
  useEffect(() => {
    const el = ref.current;
    if (el && value !== el.innerHTML) el.innerHTML = value || "";
  }, [value]);

  function run(tool) {
    const el = ref.current;
    if (!el || disabled) return;
    el.focus();

    if (tool.command === "createLink") {
      const url = window.prompt("Link to where?", "https://");
      if (!url) return;
      document.execCommand("createLink", false, url);
    } else if (tool.command === "formatBlock") {
      document.execCommand("formatBlock", false, tool.value);
    } else {
      document.execCommand(tool.command, false, null);
    }

    onChange(el.innerHTML);
  }

  return (
    <div className="richtext" data-disabled={disabled || undefined}>
      <div className="richtext-tools" role="toolbar" aria-label="Formatting" aria-controls={id}>
        {TOOLS.map((tool) => (
          <button
            key={tool.label}
            type="button"
            className="richtext-tool"
            title={tool.label}
            aria-label={tool.label}
            disabled={disabled}
            // Mousedown rather than click: clicking moves focus out of the
            // editable area first, which collapses the selection being styled.
            onMouseDown={(e) => {
              e.preventDefault();
              run(tool);
            }}
          >
            <span style={tool.style} aria-hidden="true">
              {tool.glyph}
            </span>
          </button>
        ))}
      </div>

      <div
        {...rest}
        id={id}
        ref={ref}
        className="richtext-area prose"
        contentEditable={!disabled}
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        onInput={(e) => onChange(e.currentTarget.innerHTML)}
        // Paste as plain text. Pasting from a word processor otherwise carries
        // in fonts, colours, and spans that the sanitiser strips anyway, so the
        // writer would see formatting that silently vanishes on save.
        onPaste={(e) => {
          e.preventDefault();
          const text = e.clipboardData.getData("text/plain");
          document.execCommand("insertText", false, text);
        }}
      />
    </div>
  );
}
