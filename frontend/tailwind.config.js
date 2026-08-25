/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0e1117",
        panel: "#151a21",
        raise: "#1b2028",
        line: "#28303c",
        fg: "#e8ecf2",
        muted: "#8b97a7",
        faint: "#5c6675",
        ember: "#ff7a3d",
        "ember-2": "#ffb066",
        add: "#3fb950",
        del: "#f85149",
        amber: "#d9a441",
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', "system-ui", "sans-serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        ember: "0 0 0 1px rgba(255,122,61,0.55), 0 0 26px -6px rgba(255,122,61,0.5)",
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 24px 48px -24px rgba(0,0,0,0.7)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.4s cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  plugins: [],
};
