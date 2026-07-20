export type AppLocale = "zh-CN" | "en-US";

export type MessageShape<T> = {
  [Key in keyof T]: T[Key] extends (...args: infer Args) => unknown
    ? (...args: Args) => string
    : T[Key] extends object
      ? MessageShape<T[Key]>
      : string;
};
