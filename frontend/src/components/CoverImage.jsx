/**
 * Cover images: the figure on an article, the thumbnail in a listing, and the
 * upload field in the editor.
 *
 * Every image is shown with its credit. A picture on a news page makes a claim
 * as surely as a sentence does, and the credit is its source line.
 */
import { useRef, useState } from "react";

import { ApiError, api, imageUrl } from "../api";
import { Button, Field } from "./UI";

/** The article's cover, with its credit beneath. Width and height stop the page jumping as it loads. */
export function CoverFigure({ image, priority = false, className = "" }) {
  if (!image) return null;
  return (
    <figure className={`cover ${className}`}>
      <img
        src={imageUrl(image.url)}
        alt={image.alt || ""}
        width={image.width}
        height={image.height}
        loading={priority ? "eager" : "lazy"}
        decoding="async"
      />
      {image.credit && <figcaption className="cover-credit">{image.credit}</figcaption>}
    </figure>
  );
}

/**
 * A listing's small image. Decorative there (the headline beside it says what
 * the article is), so it carries empty alt text rather than repeating it.
 */
export function EntryThumb({ image }) {
  if (!image) return null;
  return (
    <img
      className="entry-thumb"
      src={imageUrl(image.thumbUrl)}
      alt=""
      width={640}
      height={Math.round((640 * image.height) / image.width)}
      loading="lazy"
      decoding="async"
    />
  );
}

/**
 * The editor's cover image field.
 *
 * `value` is { key, url, thumbUrl, width, height } or null; `alt` and `credit`
 * are strings. Uploading happens immediately, so the writer sees exactly what
 * the server made of their file before they save.
 */
export function CoverImageField({ value, alt, credit, onChange, errors = {}, disabled }) {
  const input = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  // Already-attached images were declared when they were uploaded.
  const [declared, setDeclared] = useState(Boolean(value));

  async function choose(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError(null);
    if (!declared) {
      setError("Confirm that the image is not AI-generated first.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError("Images must be 5 MB or smaller.");
      return;
    }
    setBusy(true);
    try {
      const image = await api.uploadImage(file);
      onChange({ image });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The upload failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <fieldset className="cover-field">
      <legend className="field-label">Cover image (optional)</legend>

      {/* AI-generated images are not allowed. The server also checks each
          file's metadata for the marks AI generators leave. */}
      <label className="checkbox cover-declaration">
        <input type="checkbox" checked={declared} disabled={disabled}
          onChange={(e) => setDeclared(e.target.checked)} />
        <span>This image is not AI-generated, and I have the right to use it.</span>
      </label>

      {value ? (
        <div className="cover-preview">
          <img src={imageUrl(value.thumbUrl)} alt="" width={320} />
          <div className="row gap-4">
            <Button type="button" variant="outline" size="sm" busy={busy}
              disabled={disabled || !declared} onClick={() => input.current?.click()}>
              Replace
            </Button>
            <Button type="button" variant="quiet" size="sm" disabled={disabled || busy}
              onClick={() => onChange({ image: null })}>
              Remove
            </Button>
          </div>
        </div>
      ) : (
        <div>
          <Button type="button" variant="outline" size="sm" busy={busy}
            disabled={disabled || !declared} onClick={() => input.current?.click()}>
            Upload an image
          </Button>
          <p className="field-hint mt-2">
            JPEG, PNG or WebP, up to 5 MB. Location and camera details are removed.
            AI-generated images are not allowed, and uploads are checked for them.
          </p>
        </div>
      )}

      <input
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={choose}
      />
      {error && <p className="field-error mt-2" role="alert">{error}</p>}

      {value && (
        <div className="cover-meta mt-4">
          <Field
            label="Describe the image"
            id="coverImageAlt"
            hint="What a reader who cannot see it should know. Required to submit."
            error={errors.coverImageAlt}
          >
            {(props) => (
              <input {...props} className="input" maxLength={300} value={alt}
                disabled={disabled} onChange={(e) => onChange({ alt: e.target.value })} />
            )}
          </Field>
          <Field
            label="Credit"
            id="coverImageCredit"
            hint="Who took it, or where it came from, e.g. “Photo: Jane Doe, CC BY 4.0”. Required to submit."
            error={errors.coverImageCredit}
          >
            {(props) => (
              <input {...props} className="input" maxLength={300} value={credit}
                disabled={disabled} onChange={(e) => onChange({ credit: e.target.value })} />
            )}
          </Field>
        </div>
      )}
    </fieldset>
  );
}
