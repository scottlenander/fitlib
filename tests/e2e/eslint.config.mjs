// ESLint flat config for the Playwright suite.
// typescript-eslint uses the local TypeScript (6.0) from node_modules.
import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import globals from 'globals'
import tseslint from 'typescript-eslint'

const CLASS_SELECTOR_MESSAGE =
  'Avoid CSS class selectors: use getByRole/getByLabel/getByText, or add a data-testid to the view and use getByTestId.'

export default tseslint.config(
  {
    ignores: [
      'node_modules/',
      'test-results/',
      'playwright-report/',
      'blob-report/',
      'playwright/.cache/',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      globals: globals.node,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Forgotten awaits on Playwright calls are the most common e2e bug.
      '@typescript-eslint/no-floating-promises': 'error',
      // CSS class selectors break when styling changes. Use getByRole, getByLabel
      // or getByText; when none fits, add a data-testid to the view and use
      // getByTestId. Matches a ".class" anywhere in a locator() selector.
      'no-restricted-syntax': [
        'error',
        {
          selector:
            "CallExpression[callee.property.name='locator'] > Literal[value=/(^|[\\s>+~,(])\\.[A-Za-z_-]/]",
          message: CLASS_SELECTOR_MESSAGE,
        },
        {
          selector:
            "CallExpression[callee.property.name='locator'] > TemplateLiteral > TemplateElement[value.raw=/(^|[\\s>+~,(])\\.[A-Za-z_-]/]",
          message: CLASS_SELECTOR_MESSAGE,
        },
      ],
    },
  },
  {
    // This file is plain JS, so skip the type-aware rules.
    files: ['**/*.mjs'],
    ...tseslint.configs.disableTypeChecked,
  },
  // Last: turn off rules that conflict with Prettier's formatting.
  prettier,
)
