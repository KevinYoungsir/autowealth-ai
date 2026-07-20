import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "PingFang SC",
          "Microsoft YaHei UI",
          "Microsoft YaHei",
          "Noto Sans CJK SC",
          "Source Han Sans SC",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif"
        ],
        mono: [
          "JetBrains Mono",
          "SFMono-Regular",
          "Consolas",
          "Liberation Mono",
          "monospace"
        ]
      },
      colors: {
        ink: {
          950: "#080b10",
          900: "#0d1118",
          850: "#111722",
          800: "#151d2a"
        },
        signal: {
          cyan: "#22d3ee",
          teal: "#2dd4bf",
          green: "#74d680",
          amber: "#f5c451",
          red: "#fb7185"
        }
      },
      boxShadow: {
        panel: "0 18px 60px rgba(0, 0, 0, 0.26)"
      }
    }
  },
  plugins: []
};

export default config;
