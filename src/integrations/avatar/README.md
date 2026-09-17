# integrations/avatar — vacío a propósito

No hay adaptador aquí y **no debe haberlo todavía**. AGENTS.md §8 prohíbe
implementar un proveedor concreto de avatar mientras §1.2 siga abierto.

El contrato ya existe: `AvatarPort` en `src/models/ports.py`.

## Reparto de responsabilidades

El backend **no renderiza**. La malla, Three.js / react-three-fiber y la
reproducción viven en el frontend. Lo que `AvatarPort` aporta desde el backend
es la línea de tiempo de lip-sync (`VisemeFrame`) y el handle de sesión que el
frontend necesita para conectarse.

## Dependencia cruzada a resolver antes de implementar

El lip-sync depende del proveedor de voz (§1.1):

- Si el proveedor de TTS emite visemas o timestamps por palabra, `visemes_for`
  simplemente los traduce.
- Si no los emite, hay que derivarlos del audio **dentro de este adaptador**.

Por eso este puerto no se puede cerrar antes que el de voz.
