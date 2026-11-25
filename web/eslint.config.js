// ESLint flat config for the web app.
import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['node_modules/', 'public/', 'src/api/schema.d.ts'] },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  reactHooks.configs.flat.recommended,
  {
    languageOptions: {
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
  },
  {
    files: ['eslint.config.js'],
    ...tseslint.configs.disableTypeChecked,
  },
  // Shared code never reaches into a feature: api/, shared/ and charts/ are used by the
  // feature folders (and app/), not the other way round.
  {
    files: ['src/api/**', 'src/shared/**', 'src/charts/**'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              regex: '^\\.\\./(app|library|ride|compare|trends|map|imports|bikes|settings)(/|$)',
              message: 'Shared code must not import from a feature folder or app/.',
            },
          ],
        },
      ],
    },
  },
  // Last: turn off rules that conflict with Prettier's formatting.
  prettier,
)
