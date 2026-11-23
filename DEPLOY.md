# Publicación WILUG

Estado: código fuente cargado; servicio web y base de datos aún NO desplegados.

1. Crear base de datos PostgreSQL persistente en proveedor elegido (p. ej., Supabase) y copiar cadena de conexión con SSL. No publicar secretos.
2. En Render crear Blueprint desde este repositorio y configurar las variables requeridas: DATABASE_URL, ADMIN_PASSWORD (clave larga única), PUBLIC_URL (URL HTTPS final). SECRET_KEY se genera automáticamente.
3. Probar `/health`, evaluación completa, RUT, descarga de diploma solo aprobado, exportación Excel, acceso al panel y QR.
4. Antes de usar datos reales: revisar preguntas con instructor, establecer política de privacidad y retención de datos, reforzar autenticación y límites de intentos. El sistema es un prototipo y NO debe usarse en producción sin revisión de seguridad.

**Importante:** No usar SQLite en el almacenamiento efímero de un alojamiento gratuito: se perderían los registros tras reinicios o despliegues.
