// ESLint v9 flat config for the Section VS Code extension.
import js from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";

export default [
  {
    ignores: [
      "out/**",
      "node_modules/**",
      "scripts/**",
      "tests/vscode-mock.ts",
      "*.vsix",
      "eslint.config.mjs",
    ],
  },
  js.configs.recommended,
  {
    files: ["src/**/*.ts", "tests/**/*.ts"],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: "module",
      },
      globals: {
        // Node 18+ globals available at runtime in VS Code.
        process: "readonly",
        Buffer: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        URL: "readonly",
        URLSearchParams: "readonly",
        AbortController: "readonly",
        TextEncoder: "readonly",
        fetch: "readonly",
        Response: "readonly",
        Request: "readonly",
        RequestInit: "readonly",
        Headers: "readonly",
        console: "readonly",
        globalThis: "readonly",
      },
    },
    plugins: {
      "@typescript-eslint": tseslint,
    },
    rules: {
      ...tseslint.configs.recommended.rules,
      "no-unused-vars": "off",
      "no-undef": "off", // TS catches this; ESLint's globals list is incomplete for Node 18.
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-empty-object-type": "off",
      "no-empty": [
        "error",
        {
          allowEmptyCatch: true,
        },
      ],
    },
  },
];
