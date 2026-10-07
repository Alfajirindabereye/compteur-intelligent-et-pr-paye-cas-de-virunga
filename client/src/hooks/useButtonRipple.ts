import { useEffect } from "react";

/**
 * Effet d'onde lumineuse au clic sur n'importe quel bouton de l'application.
 *
 * L'onde est dessinée dans un calque fixe posé par-dessus le bouton : le bouton
 * lui-même n'est pas modifié (ni `position`, ni `overflow`), ce qui évite de
 * rogner les pastilles ou menus qui en dépassent.
 */
export function useButtonRipple() {
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    const onPointerDown = (event: PointerEvent) => {
      const origin = event.target instanceof Element ? event.target : null;
      const button = origin?.closest("button, [role='button'], a[data-ripple]");
      if (!(button instanceof HTMLElement)) return;
      if (button.matches(":disabled, [aria-disabled='true']")) return;
      const rect = button.getBoundingClientRect();
      if (!rect.width || !rect.height) return;

      const host = document.createElement("span");
      host.className = "btn-ripple-host";
      host.style.left = `${rect.left}px`;
      host.style.top = `${rect.top}px`;
      host.style.width = `${rect.width}px`;
      host.style.height = `${rect.height}px`;
      host.style.borderRadius = getComputedStyle(button).borderRadius;

      const size = Math.max(rect.width, rect.height) * 2.4;
      const wave = document.createElement("span");
      wave.className = "btn-ripple-wave";
      wave.style.width = wave.style.height = `${size}px`;
      wave.style.left = `${event.clientX - rect.left - size / 2}px`;
      wave.style.top = `${event.clientY - rect.top - size / 2}px`;

      host.appendChild(wave);
      document.body.appendChild(host);
      window.setTimeout(() => host.remove(), 700);
    };

    document.addEventListener("pointerdown", onPointerDown, { passive: true });
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);
}
