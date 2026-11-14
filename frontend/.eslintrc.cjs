module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
    "prettier",
  ],
  ignorePatterns: ["dist", ".eslintrc.cjs"],
  parser: "@typescript-eslint/parser",
  plugins: ["react-refresh"],
  rules: {
    "react-refresh/only-export-components": [
      "warn",
      { allowConstantExport: true },
    ],
    // Doc 07 §9.2: physical utilities are banned in tenant app code. RTL is
    // the LTR layout mirrored by the browser; a screen that does not flip has
    // a banned class and this rule names it.
    "no-restricted-syntax": [
      "error",
      {
        selector:
          "Literal[value=/(^|\\s)(ml|mr|pl|pr|left|right|text-left|text-right|space-x)-/]",
        message:
          "Physical direction utility banned (Doc 07 §9.2). Use ms-/me-/ps-/pe-/start-/end-/text-start/text-end and gap-*.",
      },
      {
        selector:
          "TemplateElement[value.raw=/(^|\\s)(ml|mr|pl|pr|left|right|text-left|text-right|space-x)-/]",
        message:
          "Physical direction utility banned (Doc 07 §9.2). Use ms-/me-/ps-/pe-/start-/end-/text-start/text-end and gap-*.",
      },
    ],
  },
  overrides: [
    {
      // The apex Platform console is English-only and LTR forever (never
      // mirrored), and marketing pages are outside the tenant app.
      files: [
        "src/features/platform/**/*.{ts,tsx}",
        "src/marketing/**/*.{ts,tsx}",
        "src/features/screens/**/*.{ts,tsx}",
      ],
      rules: { "no-restricted-syntax": "off" },
    },
  ],
};
