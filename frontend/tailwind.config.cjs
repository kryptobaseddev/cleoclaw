/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}", "./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        heading: ["var(--font-heading)", "sans-serif"],
        body: ["var(--font-body)", "sans-serif"],
        display: ["var(--font-display)", "serif"],
        label: ["var(--font-label)", "monospace"],
      },
      colors: {
        app: {
          bg: "var(--bg)",
          surface: "var(--surface)",
          "surface-muted": "var(--surface-muted)",
          "surface-strong": "var(--surface-strong)",
          "surface-highest": "var(--surface-highest)",
          border: "var(--border)",
          "border-strong": "var(--border-strong)",
          text: "var(--text)",
          "text-muted": "var(--text-muted)",
          "text-quiet": "var(--text-quiet)",
          accent: "var(--accent)",
          "accent-strong": "var(--accent-strong)",
          "accent-soft": "var(--accent-soft)",
          gold: "var(--gold)",
          "gold-soft": "var(--gold-soft)",
          success: "var(--success)",
          "success-soft": "var(--success-soft)",
          warning: "var(--warning)",
          "warning-soft": "var(--warning-soft)",
          danger: "var(--danger)",
          "danger-soft": "var(--danger-soft)",
          "nav-active": "var(--nav-active-bg)",
          "nav-active-text": "var(--nav-active-text)",
          "nav-hover": "var(--nav-hover-bg)",
        },
      },
      boxShadow: {
        glow: "var(--shadow-glow)",
        panel: "var(--shadow-panel)",
        card: "var(--shadow-card)",
      },
      backdropBlur: {
        glass: "12px",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
