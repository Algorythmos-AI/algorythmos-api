const PDFDocument = require("pdfkit");
const fs = require("fs");
const path = require("path");

const TEST_DIR = path.join(__dirname, "test-files");

if (!fs.existsSync(TEST_DIR)) {
    fs.mkdirSync(TEST_DIR);
}

function generateInvoice(id, provider, items) {
    const doc = new PDFDocument();
    const filename = `${provider}_invoice_${id}.pdf`;
    const filepath = path.join(TEST_DIR, filename);

    doc.pipe(fs.createWriteStream(filepath));

    // Header
    doc.fontSize(20).text(`${provider.toUpperCase()} INVOICE`, { align: "center" });
    doc.moveDown();
    doc.fontSize(12).text(`Invoice #: INV-${id}-${Date.now()}`);
    doc.text(`Date: ${new Date().toISOString().split("T")[0]}`);
    doc.moveDown();

    // Table Header
    doc.font("Helvetica-Bold");
    doc.text("Description", 50, 150);
    doc.text("Quantity", 250, 150);
    doc.text("Unit Price", 350, 150);
    doc.text("Total", 450, 150);
    doc.moveTo(50, 165).lineTo(550, 165).stroke();
    doc.font("Helvetica");

    // Items
    let y = 180;
    let total = 0;
    items.forEach((item) => {
        const itemTotal = item.qty * item.price;
        total += itemTotal;

        doc.text(item.desc, 50, y);
        doc.text(item.qty.toString(), 250, y);
        doc.text(`$${item.price.toFixed(2)}`, 350, y);
        doc.text(`$${itemTotal.toFixed(2)}`, 450, y);
        y += 20;
    });

    // Total
    doc.moveTo(50, y + 10).lineTo(550, y + 10).stroke();
    doc.font("Helvetica-Bold");
    doc.text(`GRAND TOTAL: $${total.toFixed(2)}`, 350, y + 25);

    doc.end();
    console.log(`Generated: ${filename}`);
}

// Generate Orange Invoices
generateInvoice("001", "orange", [
    { desc: "Fiber Plan 1GB", qty: 1, price: 49.99 },
    { desc: "Mobile 5G Data", qty: 2, price: 29.99 },
    { desc: "TV Package", qty: 1, price: 15.00 },
]);

generateInvoice("002", "orange", [
    { desc: "Business Pro Fiber", qty: 1, price: 89.99 },
    { desc: "Static IP", qty: 1, price: 10.00 },
]);

// Generate Generic Telco Invoices
generateInvoice("003", "generic_telco", [
    { desc: "Standard Internet", qty: 1, price: 39.99 },
    { desc: "Phone Line Rental", qty: 1, price: 12.50 },
]);

console.log(`\nTest files generated in ${TEST_DIR}`);
