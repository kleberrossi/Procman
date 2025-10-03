# Fonte Aptos (Opcional)

O sistema foi configurado para usar `Aptos` como primeira fonte em `--font-sans` **apenas se ela existir** no ambiente do usuário ou for servida localmente.

## Como ativar a fonte local
1. Obtenha legalmente os arquivos (licença Microsoft / Windows / Office).
2. Converta para `.woff2` se necessário.
3. Salve aqui (esta pasta):
   - `Aptos-Regular.woff2`
   - `Aptos-SemiBold.woff2`
4. No arquivo `static/css/modern-style.css`, localize o bloco comentado:
   ```css
   /* @font-face { font-family: 'Aptos'; ... } */
   ```
   e descomente as regras `@font-face`.
5. Limpe o cache do navegador (CTRL+F5) e verifique no DevTools (Computed > font-family).

## Fallback
Se os arquivos não estiverem presentes ou o bloco permanecer comentado, o navegador cairá para `Inter`, depois a cadeia do sistema.

## Motivo do design
- Mantemos fallback sólido caso a fonte não seja carregada.
- `font-display: swap` evita flash de texto invisível.

## Boas práticas
- Não inclua arquivos proprietários no repositório público.
- Se for distribuir internamente, mantenha esta pasta fora de versionamento `.gitignore` (opcional) e documente no deploy.

---
Dúvidas: verificar suporte via DevTools (aba Rendering / fonts).