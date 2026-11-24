# LocalAnonymizer 0.4.6

### Восстановление: мягкий режим срабатывает надёжно

- Галочка «Восстанавливать при нестандартном оформлении» теперь передаётся прямо в операцию восстановления, а не сохраняется отдельным вызовом. Устранена гонка, из-за которой восстановление могло пойти строгим путём сразу после включения галочки.
- Если строгий режим отказывает из-за неподдерживаемого оформления Word, программа автоматически повторяет восстановление в мягком режиме: текст и замены сохраняются, незнакомое оформление удаляется.
- Добавлены регрессии: авто-повтор, строгий успешный путь без переключения, явный аргумент галочки, а также проверка, что активный контент (OLE-части) блокируется и в мягком режиме. Полный suite — без падений.

### English

### Restore: soft mode is now reliable

- The “Restore with non-standard formatting” checkbox is passed directly into the restore operation instead of being saved in a separate call. This removes a race where restore could still run strictly right after enabling the checkbox.
- If the strict path refuses unsupported Word formatting, the app automatically retries once in soft mode: text and replacements are kept and the unrecognised formatting is removed.
- Added regressions: automatic retry, strict success without switching, explicit checkbox argument, and proof that active content (OLE parts) is still blocked in soft mode. Full suite is green.
