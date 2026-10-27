"use client";

import { Button } from "./Button";

/** Opens the browser's print dialog; choose "Save as PDF" there. The print stylesheet does the layout. */
export function PrintButton() {
  return (
    <Button variant="primary" onClick={() => window.print()} className="print:hidden">
      Save as PDF
    </Button>
  );
}
