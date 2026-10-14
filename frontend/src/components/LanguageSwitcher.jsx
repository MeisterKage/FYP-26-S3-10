/**
 * English, 中文 or Bahasa Melayu, in the masthead beside the account area so
 * it is on screen at every width.
 */
import { LANGUAGES, useI18n } from "../i18n";

export function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();
  return (
    <label className="lang-switch">
      <span className="sr-only">{t("lang.label")}</span>
      <select value={lang} onChange={(e) => setLang(e.target.value)} aria-label={t("lang.label")}>
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code} lang={l.html}>{l.short}</option>
        ))}
      </select>
    </label>
  );
}
