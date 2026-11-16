import assert from "node:assert/strict";
import test from "node:test";

import { getRoleNavigation, roleLabels } from "../lib/role-navigation.ts";

test("solo muestra navegación para permisos concedidos por el backend", () => {
  const items = getRoleNavigation([
    "patients:manage",
    "clinical:read",
    "operations:manage",
    "unknown:permission",
    "clinical:read",
  ]);

  assert.deepEqual(
    items.map((item) => item.permission),
    ["clinical:read", "patients:manage", "operations:manage"],
  );
  assert.equal(items[0].label, "Dashboard médico");
  assert.equal(items[0].sectionId, "doctor-dashboard");
  const serviceItem = items.find((item) => item.permission === "operations:manage");
  assert.equal(serviceItem?.label, "Servicio");
  assert.equal(serviceItem?.sectionId, "service-queue");
});

test("no inventa áreas cuando el usuario aún no tiene permisos", () => {
  assert.deepEqual(getRoleNavigation([]), []);
});

test("muestra una sola entrada de agenda cuando el usuario puede gestionarla", () => {
  const items = getRoleNavigation(["appointments:read", "appointments:manage"]);
  assert.equal(items.length, 1);
  assert.equal(items[0].permission, "appointments:manage");
  assert.equal(items[0].label, "Ventanilla");
  assert.equal(items[0].sectionId, "reception");
});

test("define etiquetas para los cinco roles del esquema de autorización", () => {
  assert.deepEqual(Object.keys(roleLabels).sort(), [
    "administrator",
    "doctor",
    "receptionist",
    "service",
    "superadmin",
  ]);
});
