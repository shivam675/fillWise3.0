// @ts-check
/** @type {import("eslint").Linter.Config} */
module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: { jsx: true },
    project: ["./tsconfig.json"],
    tsconfigRootDir: __dirname,
  },
  settings: {
    react: { version: "detect" },
  },
  plugins: [
    "@typescript-eslint",
    "react",
    "react-hooks",
    "react-refresh",
    "jsx-a11y",
    "import",
  ],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:@typescript-eslint/recommended-requiring-type-checking",
    "plugin:react/recommended",
    "plugin:react/jsx-runtime",
    "plugin:react-hooks/recommended",
    "plugin:jsx-a11y/recommended",
    "plugin:import/typescript",
  ],
  rules: {
    // TypeScript
    "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/explicit-function-return-type": "off",
    "@typescript-eslint/explicit-module-boundary-types": "off",
    "@typescript-eslint/no-non-null-assertion": "warn",
    "@typescript-eslint/no-floating-promises": "error",
    "@typescript-eslint/await-thenable": "error",
    "@typescript-eslint/no-misused-promises": [
      "error",
      { checksVoidReturn: { attributes: false } },
    ],

    // React
    "react/prop-types": "off",
    "react/display-name": "off",
    "react-refresh/only-export-components": [
      "warn",
      { allowConstantExport: true },
    ],

    // React Hooks
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "warn",

    // Imports
    "import/no-duplicates": "error",
    "import/order": [
      "warn",
      {
        groups: [
          "builtin",
          "external",
          "internal",
          ["parent", "sibling", "index"],
        ],
        "newlines-between": "always",
        alphabetize: { order: "asc", caseInsensitive: true },
      },
    ],

    // General
    "no-console": ["warn", { allow: ["warn", "error"] }],
    "eqeqeq": ["error", "always"],
    "prefer-const": "error",
    "no-var": "error",
  },
  ignorePatterns: [
    "dist/",
    "node_modules/",
    "coverage/",
    "playwright-report/",
    "*.config.js",
    "*.config.ts",
    "postcss.config.js",
  ],
};
