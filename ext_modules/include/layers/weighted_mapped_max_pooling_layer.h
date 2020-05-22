#ifndef WEIGHTED_MAPPED_MAX_POOLING_LAYER_H_
#define WEIGHTED_MAPPED_MAX_POOLING_LAYER_H_

#include <torch/extension.h>
#include <vector>

#include "cuda_helper.h"
#include "enums.h"

namespace spherical {

#ifndef __NO_CUDA__  // CUDA compilation only
namespace cuda {
std::vector<torch::Tensor> WeightedMappedMaxPoolForward(
    torch::Tensor input, torch::Tensor sample_map, torch::Tensor interp_weights,
    int kernel_size, InterpolationType interpolation);

torch::Tensor WeightedMappedMaxPoolBackward(
    torch::Tensor input, torch::Tensor idx_mask, torch::Tensor sample_map,
    torch::Tensor interp_weights, int inputHeight, int inputWidth,
    int kernel_size, InterpolationType interpolation);
}  // namespace cuda
#endif

namespace cpu {
std::vector<torch::Tensor> WeightedMappedMaxPoolForward(
    torch::Tensor input, torch::Tensor sample_map, torch::Tensor interp_weights,
    int kernel_size, InterpolationType interpolation);

torch::Tensor WeightedMappedMaxPoolBackward(
    torch::Tensor input, torch::Tensor idx_mask, torch::Tensor sample_map,
    torch::Tensor interp_weights, int inputHeight, int inputWidth,
    int kernel_size, InterpolationType interpolation);
}  // namespace cpu

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
// CALL FUNCTION IMPLEMENTATIONS
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *

std::vector<torch::Tensor> WeightedMappedMaxPoolForward(
    torch::Tensor input, torch::Tensor sample_map, torch::Tensor interp_weights,
    int kernel_size, InterpolationType interpolation) {
  CHECK_CONTIGUOUS(input);
  CHECK_CONTIGUOUS(sample_map);
  CHECK_CONTIGUOUS(interp_weights);

#ifndef __NO_CUDA__  // CUDA compilation only
  if (input.is_cuda()) {
    CHECK_CUDA(input);
    CHECK_CUDA(sample_map);
    CHECK_CUDA(interp_weights);
    return cuda::WeightedMappedMaxPoolForward(input, sample_map, interp_weights,
                                              kernel_size, interpolation);
  } else
#endif
  {
    CHECK_CPU(input);
    CHECK_CPU(sample_map);
    CHECK_CPU(interp_weights);
    return cpu::WeightedMappedMaxPoolForward(input, sample_map, interp_weights,
                                             kernel_size, interpolation);
  }
}

torch::Tensor WeightedMappedMaxPoolBackward(
    torch::Tensor input, torch::Tensor idx_mask, torch::Tensor sample_map,
    torch::Tensor interp_weights, int inputHeight, int inputWidth,
    int kernel_size, InterpolationType interpolation) {
  CHECK_CONTIGUOUS(input);
  CHECK_CONTIGUOUS(idx_mask);
  CHECK_CONTIGUOUS(sample_map);
  CHECK_CONTIGUOUS(interp_weights);

#ifndef __NO_CUDA__  // CUDA compilation only
  if (input.is_cuda()) {
    CHECK_CUDA(input);
    CHECK_CUDA(idx_mask);
    CHECK_CUDA(sample_map);
    CHECK_CUDA(interp_weights);
    return cuda::WeightedMappedMaxPoolBackward(
        input, idx_mask, sample_map, interp_weights, inputHeight, inputWidth,
        kernel_size, interpolation);
  } else
#endif
  {
    CHECK_CPU(input);
    CHECK_CPU(idx_mask);
    CHECK_CPU(sample_map);
    CHECK_CPU(interp_weights);
    return cpu::WeightedMappedMaxPoolBackward(
        input, idx_mask, sample_map, interp_weights, inputHeight, inputWidth,
        kernel_size, interpolation);
  }
}

}  // namespace spherical

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("weighted_mapped_max_pool", &spherical::WeightedMappedMaxPoolForward,
        "Mapped max pooling operation");
  m.def("weighted_mapped_max_unpool", &spherical::WeightedMappedMaxPoolBackward,
        "Mapped max unpooling operation");
}

#endif