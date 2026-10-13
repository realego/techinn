import { copyFile, readFile, writeFile } from "node:fs/promises";
import sharp from "sharp";

const root = new URL("../public/", import.meta.url);
const source = await readFile(new URL("techinn-favicon.svg", root));
const icons = [];
for (const size of [16, 32, 48]) {
  const png = await sharp(source).resize(size, size).png().toBuffer();
  icons.push({ size, png });
  await writeFile(new URL(`techinn-icon-${size}-v2.png`, root), png);
}

// Standard multi-resolution ICO, with PNG-encoded entries.
const header = Buffer.alloc(6 + icons.length * 16);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(icons.length, 4);
let offset = header.length;
icons.forEach(({ size, png }, index) => {
  const entry = 6 + index * 16;
  header[entry] = size;
  header[entry + 1] = size;
  header.writeUInt16LE(1, entry + 4);
  header.writeUInt16LE(32, entry + 6);
  header.writeUInt32LE(png.length, entry + 8);
  header.writeUInt32LE(offset, entry + 12);
  offset += png.length;
});
await writeFile(new URL("favicon.ico", root), Buffer.concat([header, ...icons.map(({ png }) => png)]));
await sharp(source).resize(180, 180).png().toFile(new URL("techinn-apple-icon-v2.png", root).pathname);
await copyFile(new URL("techinn-apple-icon-v2.png", root), new URL("apple-touch-icon.png", root));
await copyFile(new URL("techinn-favicon.svg", root), new URL("favicon.svg", root));
console.log("Built TechInn SVG, PNG, ICO, and Apple icons.");
