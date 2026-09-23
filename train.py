import torch

from model import SimpleCNN


if __name__ == "__main__":
    print("--- 開始輕量驗證 ---")
    
    # 建立模型實例
    model = SimpleCNN(input_channels=3, hidden_size=128, output_size=2)  # 如果你的 class 叫其他名字（例如 MyModel），請換成你的模型名稱
    
    # 假造一筆極小的測試資料 (Batch Size: 2, 3 通道, 32x32 圖片)
    # 若你的輸入不是 3x32x32，可根據自己的維度修改
    dummy_input = torch.randn(2, 3, 32, 32)
    
    # 測試前向傳播 (Forward pass)
    output = model(dummy_input)
    
    print("模型測試成功！輸出維度為:", output.shape)