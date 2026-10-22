from PIL import Image

from app import notion
from app.runner import _is_meaningful_snapshot


def test_screenshot_detection_and_notion_resize(tmp_path, monkeypatch):
    monkeypatch.setattr(notion, 'OUTPUT_DIR', tmp_path)
    path = tmp_path / 'snapshot.png'
    image = Image.new('RGB', (100, 80), 'white')
    for x in range(50):
        for y in range(80):
            image.putpixel((x,y), (0,0,0))
    image.save(path)
    assert _is_meaningful_snapshot(path)
    with Image.open(notion._resized_image_path(path)) as resized:
        assert resized.size == (50,40)
    Image.new('RGB',(100,80),'white').save(path)
    assert not _is_meaningful_snapshot(path)
