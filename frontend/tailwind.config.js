/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#12201B",
        paper: "#F5F6F1",
        forest: {
          DEFAULT: "#1F4B3F",
          dark: "#153A30",
          light: "#2C6551",
        },
        brass: {
          DEFAULT: "#B8863B",
          light: "#D9AE6B",
        },
        rust: "#B23A2E",
        violet: "#6B4E71",
        slate: {
          DEFAULT: "#5B6B66",
          light: "#8A9793",
        },
        line: "#DBDED4",
      },
      fontFamily: {
        display: ["'Fraunces'", "serif"],
        body: ["'Inter'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      borderRadius: {
        seal: "9999px",
      },
    },
  },
  plugins: [],
};
