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
      },
      colors: {
        app: {
          bg: "var(--bg)",
          surface: "var(--surface)",
          "surface-muted": "var(--surface-muted)",
          "surface-strong": "var(--surface-strong)",
          border: "var(--border)",
          "border-strong": "var(--border-strong)",
          text: "var(--text)",
          "text-muted": "var(--text-muted)",
          "text-quiet": "var(--text-quiet)",
          accent: "var(--accent)",
          "accent-strong": "var(--accent-strong)",
          "accent-soft": "var(--accent-soft)",
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
    },
  },
  plugins: [require("tailwindcss-animate")],
};
