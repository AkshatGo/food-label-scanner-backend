"""Generate synthetic, visibly named OCR test labels; never shown as real scans."""
from PIL import Image, ImageDraw, ImageFont

font = ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf', 25)
for position, lines in {
    'front': ['Test Oat Biscuits', 'Brand: TEST FIXTURE', 'Net weight 100g'],
    'back': ['Test Oat Biscuits', 'Ingredients: Wheat Flour, Sugar, Palm Oil, Salt',
             'Contains Wheat', 'Nutritional Information per 100g', 'Energy 480 kcal',
             'Protein 6 g', 'Total Carbohydrate 62 g', 'Total Sugars 18 g',
             'Added Sugars 15 g', 'Total Fat 20 g', 'Saturated Fat 6 g',
             'Sodium 420 mg', 'Dietary Fibre 2 g', 'FSSAI Lic. No. 10012345678901',
             'Batch No. TEST123', 'Best Before 6 months', 'Net weight 100g']
}.items():
    image = Image.new('RGB', (950, 1050), 'white')
    draw = ImageDraw.Draw(image)
    for number, line in enumerate(lines):
        draw.text((35, 35 + number * 53), line, font=font, fill='black')
    image.save(f'/tmp/labelens-test-{position}.png')
