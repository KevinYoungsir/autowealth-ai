import { enUSMessages } from "./messages/en-US";
import { zhCNMessages } from "./messages/zh-CN";
import type { AppLocale } from "./types";

export const DEFAULT_UI_LOCALE: AppLocale = "zh-CN";

export function getMessages(locale: AppLocale = DEFAULT_UI_LOCALE) {
  return locale === "zh-CN" ? zhCNMessages : enUSMessages;
}

export const ui = zhCNMessages;
export { machineLabel, runReasonLabel } from "./machine-labels";
export type { AppLocale } from "./types";
