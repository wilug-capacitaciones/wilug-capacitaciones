# WILUG · Evaluación de Uso y Manejo de Extintores

Aplicación web para registrar participantes, evaluar 20 preguntas, aprobar desde 14 respuestas correctas (70%), emitir diplomas PDF solo a aprobados y exportar resultados Excel.

**Estado:** código en preparación. **No está desplegada ni lista para recibir datos reales.**

## Seguridad
- No subir datos de trabajadores, RUT reales, contraseñas ni archivos `.env`.
- Configurar `SECRET_KEY`, `ADMIN_PASSWORD`, `DATABASE_URL` y `COOKIE_SECURE=1` en el alojamiento privado.
- Usar PostgreSQL con TLS y HTTPS. Revisar controles anti-CSRF, limitación de intentos de acceso y protección de datos antes de publicar.
- Revisar el cuestionario con el instructor y los procedimientos del cliente.

## Despliegue
Pendiente de preparar y validar el servidor y la base de datos. Este repositorio público contiene exclusivamente código y documentación sin credenciales.