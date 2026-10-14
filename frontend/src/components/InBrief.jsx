/**
 * "In brief": the key points of a long article.
 *
 * The points are the article's own sentences, chosen by the server, so the box
 * can never say anything the article does not. Listening is handled by
 * ArticleAudio, which reads either these points or the whole article and tells
 * this box which point is being read. When a text-to-speech service is
 * connected on the server, its recording plays here instead.
 */
import { useI18n } from "../i18n";
export function InBrief({ brief, current = -1 }) {
  const narration = brief.narration || {};
  const { t } = useI18n();

  return (
    <aside className="brief" aria-labelledby="brief-title">
      <div className="brief-head">
        <p className="label" id="brief-title">
          {t("brief.title")} <span className="brief-time">· {t("brief.minRead", { n: brief.readingMinutes })}</span>
        </p>
      </div>
      <ul className="brief-points">
        {brief.points.map((point, i) => (
          <li key={i} className={current === i ? "is-reading" : undefined}>
            {point}
          </li>
        ))}
      </ul>
      {narration.mode === "audio" && narration.url && (
        <audio className="brief-audio" controls preload="none" src={narration.url}>
          Your browser cannot play this recording.
        </audio>
      )}
      <p className="brief-method">{t("brief.method")}</p>
    </aside>
  );
}
