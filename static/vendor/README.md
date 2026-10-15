# Original UI assets

These assets preserve the pre-existing UI while serving everything from the same origin under the application's CSP:

- SQL Formatter 15.8.2: original unpkg bundle; MIT license included.
- Highlight.js 11.9.0: original cdnjs common bundle; BSD license included.
- Instrument Serif, Inter, JetBrains Mono: original Google Fonts families; font CSS/files and OFL licenses included.
- Tailwind CSS 3.4.17: precompiled into `../style.css` using the original theme; MIT license included.

No npm/Node process or CDN is needed at application runtime. To rebuild styles from the repository root after changing utility classes:

```bash
npx --yes tailwindcss@3.4.17 --config scripts/tailwind.config.cjs --input static/ui-custom.css --output static/style.css --minify
```

`../ui-custom.css` contains the original custom styles plus narrow-screen/accessibility fixes. Fonts were downloaded from the same Google Fonts family URL previously used in `index.html`; the CSS references only local files.
