#PyTorch Resnet code repurposed for 1D Convolutions
from torch import Tensor, nn
from typing import Type, Callable, Union, List, Optional, Dict

__all__ = ["resnet18", "resnet34", "resnet50", "resnet101",
           "resnet152", "resnext50_32x4d", "resnext101_32x8d",
           "wide_resnet50_2", "wide_resnet101_2"]

def conv3(in_channels: int, out_channels: int, stride: int = 1, groups: int = 1, dilation: int = 1) -> nn.Conv1d:
  return nn.Conv1d(in_channels, out_channels, kernel_size=3, stride=stride,
                    padding=dilation, groups=groups, bias=False, dilation=dilation)

def conv1(in_channels: int, out_channels: int, stride: int = 1) -> nn.Conv1d:
  return nn.Conv1d(in_channels, out_channels, kernel_size=1, stride=stride, bias=False)


class BasicBlock(nn.Module):
  expansion: int = 1

  def __init__(self, in_channels: int, out_channels: int, stride: int = 1,
               downsample: Optional[nn.Module] = None, groups: int = 1, base_width: int = 64,
               dilation: int = 1, norm_layer: Optional[Callable[..., nn.Module]] = None) -> None:
    super(BasicBlock, self).__init__()
    if groups != 1 or base_width != 64:
      print("groups", groups)
      print("base_width", base_width)
      raise ValueError("BasicBlock only supports groups=1 and base_width=64")
    if dilation > 1:
      raise NotImplementedError("Dilation > 1 not supported in BasicBlock")

    # Both self.conv1 and self.downsample layers downsample the input when stride != 1
    self.conv1 = conv3(in_channels, out_channels, stride)
    self.bn1 = norm_layer(out_channels)
    self.relu = nn.ReLU(inplace=True)
    self.conv2 = conv3(out_channels, out_channels)
    self.bn2 = norm_layer(out_channels)
    self.downsample = downsample
    self.stride = stride

  def forward(self, x: Tensor) -> Tensor:
    identity = x

    out = self.conv1(x)
    out = self.bn1(out)
    out = self.relu(out)

    out = self.conv2(out)
    out = self.bn2(out)

    if self.downsample is not None:
        identity = self.downsample(x)

    out += identity
    out = self.relu(out)

    return out


class Bottleneck(nn.Module):
  # Bottleneck in torchvision places the stride for downsampling at 3x3 convolution(self.conv2)
  # while original implementation places the stride at the first 1x1 convolution(self.conv1)
  # according to "Deep residual learning for image recognition"https://arxiv.org/abs/1512.03385.
  # This variant is also known as ResNet V1.5 and improves accuracy according to
  # https://ngc.nvidia.com/catalog/model-scripts/nvidia:resnet_50_v1_5_for_pytorch.
  expansion: int = 4

  def __init__(self, in_channels: int, out_channels: int, stride: int = 1,
               downsample: Optional[nn.Module] = None, groups: int = 1, base_width: int = 64,
               dilation: int = 1, norm_layer: Optional[Callable[..., nn.Module]] = None) -> None:
    super(Bottleneck, self).__init__()

    if norm_layer is None:
        norm_layer = nn.BatchNorm1d
    width = int(out_channels * (base_width / 64.)) * groups

    # Both self.conv2 and self.downsample layers downsample the input when stride != 1
    self.conv1 = conv1(in_channels, width)
    self.bn1 = norm_layer(width)
    self.conv2 = conv3(width, width, stride, groups, dilation)
    self.bn2 = norm_layer(width)
    self.conv3 = conv1(width, out_channels * self.expansion)
    self.bn3 = norm_layer(out_channels * self.expansion)
    self.relu = nn.ReLU(inplace=True)
    self.downsample = downsample
    self.stride = stride

  def forward(self, x: Tensor) -> Tensor:
    identity = x

    out = self.conv1(x)
    out = self.bn1(out)
    out = self.relu(out)

    out = self.conv2(out)
    out = self.bn2(out)
    out = self.relu(out)

    out = self.conv3(out)
    out = self.bn3(out)

    if self.downsample is not None:
      identity = self.downsample(x)

    out += identity
    out = self.relu(out)

    return out


class ResNet(nn.Module):
  def __init__(self, block: Type[Union[BasicBlock, Bottleneck]], layers: List[int], num_classes,
               num_input_channels: int, input_size, zero_init_residual: bool = False,
               groups: int = 1, width_per_group: int = 64,
               replace_stride_with_dilation: Optional[List[bool]] = None,
               norm_layer: Optional[Callable[..., nn.Module]] = None) -> None:
    super(ResNet, self).__init__()

    if norm_layer is None:
      norm_layer = nn.BatchNorm1d
    self._norm_layer = norm_layer
    self.in_dim = num_input_channels
    self.in_channels = 64
    self.dilation = 1
    if replace_stride_with_dilation is None:
      # each element in the tuple indicates if we should replace
      # the 2x2 stride with a dilated convolution instead
      replace_stride_with_dilation = [False, False, False]
    if len(replace_stride_with_dilation) != 3:
      raise ValueError("replace_stride_with_dilation should be None "
                        "or a 3-element tuple, got {}".format(replace_stride_with_dilation))

    self.groups = groups
    self.base_width = width_per_group
    self.conv1 = nn.Conv1d(self.in_dim, self.in_channels, kernel_size=7, stride=2, padding=3,
                           bias=False)
    self.bn1 = norm_layer(self.in_channels)
    self.relu = nn.ReLU(inplace=True)
    self.maxpool = nn.MaxPool1d(kernel_size=3, stride=2, padding=1)
    self.layer1 = self._make_layer(block, 64, layers[0])
    self.layer2 = self._make_layer(block, 128, layers[1], stride=2,
                                    dilate=replace_stride_with_dilation[0])
    self.layer3 = self._make_layer(block, 256, layers[2], stride=2,
                                    dilate=replace_stride_with_dilation[1])
    self.layer4 = self._make_layer(block, 512, layers[3], stride=2,
                                    dilate=replace_stride_with_dilation[2])
    self.avgpool = nn.AdaptiveAvgPool1d(1)
    self.flatten = nn.Flatten()
    fc_input_size = 512 * block.expansion * (4 if input_size == 64 else 1)
#     print("fc_input_size", fc_input_size)
#     print("block.expansion", block.expansion)
    
    self.fc = nn.Linear(fc_input_size, out_features=num_classes)

    for m in self.modules():
      if isinstance(m, nn.Conv1d):
        nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
      elif isinstance(m, (nn.BatchNorm1d, nn.GroupNorm)):
        nn.init.constant_(m.weight, 1)
        nn.init.constant_(m.bias, 0)

    # Zero-initialize the last BN in each residual branch,
    # so that the residual branch starts with zeros, and each residual block behaves like an identity.
    # This improves the model by 0.2~0.3% according to https://arxiv.org/abs/1706.02677
    if zero_init_residual:
      for m in self.modules():
        if isinstance(m, Bottleneck):
          nn.init.constant_(m.bn3.weight, 0)  # type: ignore[arg-type]
        elif isinstance(m, BasicBlock):
          nn.init.constant_(m.bn2.weight, 0)  # type: ignore[arg-type]

    self.out_dim = 2048 if block is Bottleneck else 512

  def _make_layer(self, block: Type[Union[BasicBlock, Bottleneck]], out_channels: int, blocks: int,
                  stride: int = 1, dilate: bool = False) -> nn.Sequential:
    norm_layer = self._norm_layer
    downsample = None
    previous_dilation = self.dilation
    if dilate:
      self.dilation *= stride
      stride = 1
    if stride != 1 or self.in_channels != out_channels * block.expansion:
      downsample = nn.Sequential(
        conv1(self.in_channels, out_channels * block.expansion, stride),
        norm_layer(out_channels * block.expansion)
      )

    layers = []
    layers.append(block(self.in_channels, out_channels, stride, downsample, self.groups,
                        self.base_width, previous_dilation, norm_layer))
    self.in_channels = out_channels * block.expansion
    for _ in range(1, blocks):
      layers.append(block(self.in_channels, out_channels, groups=self.groups,
                          base_width=self.base_width, dilation=self.dilation,
                          norm_layer=norm_layer))

    return nn.Sequential(*layers)

  def _forward_impl(self, x: Tensor, layer=7) -> Tensor:
    if layer <= 0: 
        return x
    out = self.relu(self.bn1(self.conv1(x)))
    if layer == 1:
        return out
    out = self.maxpool(out)
    out = self.layer1(out)
    if layer == 2:
        return out
    out = self.layer2(out)
    if layer == 3:
        return out
    out = self.layer3(out)
    if layer == 4:
        return out
    out = self.layer4(out)
    if layer == 5:
        return out
    out = self.avgpool(out)
    out = self.flatten(out)
#     print("out after layer 6", out.shape)
    if layer == 6:
        return out
    out = self.fc(out)
    return out
#     x = self.conv1(x)
#     x = self.bn1(x)
#     x = self.relu(x)
#     x = self.maxpool(x)

#     x = self.layer1(x)
#     x = self.layer2(x)
#     x = self.layer3(x)
#     x = self.layer4(x)

#     x = self.avgpool(x)
#     x = self.flatten(x)

#     return x

  def forward(self, x: Tensor, layer=7) -> Tensor:
    return self._forward_impl(x, layer)

def ResNet18(num_classes, num_channels: int, input_size=32, **kwargs: Dict) -> ResNet:
#     ResNet(BasicBlock, [2,2,2,2], num_classes, num_channels=num_channels, 
#                   input_size=input_size)
  return ResNet(BasicBlock, [2, 2, 2, 2], num_classes, num_channels, input_size, **kwargs)

def resnet34(num_input_channels: int, **kwargs: Dict) -> ResNet:
  return ResNet(BasicBlock, [3, 4, 6, 3], num_input_channels, **kwargs)

def resnet50(num_input_channels: int, **kwargs: Dict) -> ResNet:
  return ResNet(Bottleneck, [3, 4, 6, 3], num_input_channels, **kwargs)

def resnet101(num_input_channels: int, **kwargs: Dict) -> ResNet:
  return ResNet(Bottleneck, [3, 4, 23, 3], num_input_channels, **kwargs)

def resnet152(num_input_channels: int, **kwargs: Dict) -> ResNet:
  return ResNet(Bottleneck, [3, 8, 36, 3], num_input_channels, **kwargs)

def resnext50_32x4d(num_input_channels: int, **kwargs: Dict) -> ResNet:
  kwargs["groups"] = 32
  kwargs["width_per_group"] = 4
  return ResNet(Bottleneck, [3, 4, 6, 3], num_input_channels, **kwargs)

def resnext101_32x8d(num_input_channels: int, **kwargs: Dict) -> ResNet:
  kwargs["groups"] = 32
  kwargs["width_per_group"] = 8
  return ResNet(Bottleneck, [3, 4, 23, 3], num_input_channels, **kwargs)

def wide_resnet50_2(num_input_channels: int, **kwargs: Dict) -> ResNet:
  kwargs["width_per_group"] = 64 * 2
  return ResNet(Bottleneck, [3, 4, 6, 3], num_input_channels, **kwargs)

def wide_resnet101_2(num_input_channels: int, **kwargs: Dict) -> ResNet:
  kwargs["width_per_group"] = 64 * 2
  return ResNet(Bottleneck, [3, 4, 23, 3], num_input_channels, **kwargs)