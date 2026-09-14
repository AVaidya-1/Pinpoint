# Recommended Test PDFs

## 1. Hardware Pinouts, Dimensions & Schematics: Raspberry Pi Pico Datasheet
* **File URL:** https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf
* **File Size:** ~1.2 MB
* **Recommended Page Range:** Pages 5–10, 16 (Total: 7 pages)
* **What It Tests:**
  * **Diagram (Pinout & Geometry):** Asking "Which pins support ADC inputs?" or "Where is the ground pad next to pin 20?" (Page 6).
  * **Table (Operating Limits & Power):** Asking "Where are the recommended operating conditions for VBUS and VSYS?" (Page 8–9). Evaluates row, column header, and unit localization.
  * **CAD / Mechanical Drawing:** Asking "Where is the dimension specifying the board length and width?" (Page 16).
  * **Negative Control (Absent Target):** Asking "Where is the RJ-45 Ethernet PHY controller located?" (Tests whether the model returns `not_found` rather than hallucinating coordinates).

## 2. Electronic Curves, Block Diagrams & Tables: Texas Instruments NE555 Precision Timer
* **File URL:** https://ti.com/lit/ds/symlink/ne555.pdf
* **File Size:** ~1.5 MB
* **Recommended Page Range:** Pages 1, 5, 7–9, 11 (Total: 6 pages)
* **What It Tests:**
  * **Functional Block Diagram:** Asking "Where is the internal flip-flop and discharge transistor connected?" (Page 1).
  * **Specification Table:** Asking "Where is the supply voltage operating range specified for the NE555?" (Page 5).
  * **Chart / Graphical Curves:** Asking "Where is the plot showing frequency versus timing resistance?" or "Where is the curve for low-level output voltage vs output current?" (Pages 7–9). Requires the model to capture the curve along with its axes and legend.
  * **Application Circuit Schematic:** Asking "Which schematic shows the astable multivibrator wiring?" (Page 11).

## 3. Troubleshooting Flowchart: Lippert Electric Step Diagnostics
* **File URL:** https://support.lci1.com/documents/ccd-0011565
* **File Size:** ~200 KB
* **Recommended Page Range:** Pages 1–4 (Total: 4 pages)
* **What It Tests:**
  * **Flowchart Branches (Core MVP Demo Target):** Asking "Where does the 'No' branch go if battery voltage is not 12V or more?" or "Where does the path lead if there is 0V on the yellow wire?" (Pages 1–2).
  * **Decision Nodes:** Asking "Where is the test for the override switch being ON?"
  * **Multi-Box Evidence Groups:** Flowchart queries require highlighting both the decision diamond and its destination remedy box.

## 4. Physical Photos & Hardware Assemblies: Prusa i3 MK3S+ 3D Printer Handbook
* **File URL:** https://bu.edu/eng/files/2022/10/prusa3d_manual_mk3s_en.pdf
* **File Size:** ~18 MB
* **Recommended Page Range:** Pages 8–10, 48–52 (Total: 7 pages)
* **What It Tests:**
  * **Photo / Mechanical Assembly:** Asking "Where is the filament sensor located on the extruder assembly picture?" (Pages 8–9).
  * **Callout Labels:** Asking "Where is the LCD control knob shown in the overview diagram?"
  * **Text Lookup:** Asking "Where does the handbook describe the initial calibration wizard?"
  * **Negative Control:** Asking "Where are the instructions for replacing the dual-extruder laser mirror?" (Absent component).

## 5. Instrument Schematics & Aerodynamic Plots: FAA Pilot’s Handbook (Excerpt)
* **File URL:** https://data.ntsb.gov/Docket/Document/docBLOB?ID=40378961&FileExtension=.PDF&FileName=FAA%20Pilot%27s%20Handbook%20of%20Aeronautical%20Knowledge%20Excerpt-Master.PDF
* **File Size:** ~8.5 MB
* **Recommended Page Range:** Pages 1–6 (Total: 6 pages)
* **What It Tests:**
  * **Placards & Dial Markings:** Asking "Where is the airspeed indicator marked with the single-engine best rate-of-climb speed (Blue Line)?"
  * **Schematic Routing:** Asking "Where is the diagram showing the pitot line connected to the airspeed indicator?"

---

## Test Suite Mapping

| PDF Source | Category | Sample Agent Prompt | Expected Bounding Target |
|---|---|---|---|
| **Raspberry Pi Pico** | Diagram / Pinout | "Where is the UART0 TX pin located on the pin diagram?" | Physical pin 1 / GP0 on the page 6 diagram. |
| **Raspberry Pi Pico** | Dimension CAD | "Where are the physical outer dimensions of the board shown?" | 21 mm × 51 mm dimensions on the mechanical drawing. |
| **TI NE555** | Curve / Chart | "Where is the curve showing frequency versus timing resistance?" | Line plot including axis labels ($R_A + 2R_B$, capacitance curves). |
| **TI NE555** | Table | "Where does the datasheet list the maximum supply voltage rating?" | Absolute Maximum Ratings table row for $V_{CC}$. |
| **Lippert Diagnostics** | Flowchart | "Where does the failed battery voltage check direct the technician?" | Decision diamond leading to "Recharge battery or repair charging system". |
| **Prusa MK3S+** | Photo / Image | "Where is the extruder motor in the printer overview image?" | Stepper motor on the print head assembly. |
| **Any Document** | Absent / Negative | "Where is the optical heart rate sensor connected?" | No highlighted box; returns `not_found` / `no_evidence`. |