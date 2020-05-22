#ifndef WEIGHTED_RESAMPLE_LAYER_H_
#define WEIGHTED_RESAMPLE_LAYER_H_

#include <torch/extension.h>
#include <vector>

#include "cuda_helper.h"
#include "enums.h"

namespace spherical {

#ifndef __NO_CUDA__  // CUDA compilation only
namespace cuda {

torch::Tensor WeightedResampleToMap(torch::Tensor input,
                                    torch::Tensor sample_map,
                                    torch::Tensor interp_weights,
                                    int outputHeight, int outputWidth,
                                    InterpolationType interpolation);

torch::Tensor WeightedResampleFromMap(torch::Tensor grad_output,
                                      torch::Tensor sample_map,
                                      torch::Tensor interp_weights,
                                      InterpolationType interpolation);
}  // namespace cuda
#endif

namespace cpu {

torch::Tensor WeightedResampleToMap(torch::Tensor input,
                                    torch::Tensor sample_map,
                                    torch::Tensor interp_weights,
                                    int outputHeight, int outputWidth,
                                    InterpolationType interpolation);

torch::Tensor WeightedResampleFromMap(torch::Tensor grad_output,
                                      torch::Tensor sample_map,
                                      torch::Tensor interp_weights,
                                      InterpolationType interpolation);

}  // namespace cpu

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
// CALL FUNCTION IMPLEMENTATIONS
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *

torch::Tensor WeightedResampleToMap(torch::Tensor input,
                                    torch::Tensor sample_map,
                                    torch::Tensor interp_weights,
                                    int outputHeight, int outputWidth,
                                    InterpolationType interpolation) {
  CHECK_CONTIGUOUS(input);
  CHECK_CONTIGUOUS(sample_map);
  CHECK_CONTIGUOUS(interp_weights);

#ifndef __NO_CUDA__  // CUDA compilation only
  if (input.is_cuda()) {
    CHECK_CUDA(input);
    CHECK_CUDA(sample_map);
    CHECK_CUDA(interp_weights);
    return cuda::WeightedResampleToMap(input, sample_map, interp_weights,
                                       outputHeight, outputWidth,
                                       interpolation);
  } else
#endif
  {
    CHECK_CPU(input);
    CHECK_CPU(sample_map);
    CHECK_CPU(interp_weights);
    return cpu::WeightedResampleToMap(input, sample_map, interp_weights,
                                      outputHeight, outputWidth, interpolation);
  }
}

torch::Tensor WeightedResampleFromMap(torch::Tensor grad_output,
                                      torch::Tensor sample_map,
                                      torch::Tensor interp_weights,
                                      InterpolationType interpolation) {
  CHECK_CONTIGUOUS(grad_output);
  CHECK_CONTIGUOUS(sample_map);
  CHECK_CONTIGUOUS(interp_weights);

#ifndef __NO_CUDA__  // CUDA compilation only
  if (grad_output.is_cuda()) {
    CHECK_CUDA(grad_output);
    CHECK_CUDA(sample_map);
    CHECK_CUDA(interp_weights);
    return cuda::WeightedResampleFromMap(grad_output, sample_map,
                                         interp_weights, interpolation);
  } else
#endif
  {
    CHECK_CPU(grad_output);
    CHECK_CPU(sample_map);
    CHECK_CPU(interp_weights);
    return cpu::WeightedResampleFromMap(grad_output, sample_map, interp_weights,
                                        interpolation);
  }
}

}  // namespace spherical

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("weighted_resample_to_map", &spherical::WeightedResampleToMap,
        "Resampling operation");
  m.def("weighted_resample_from_map", &spherical::WeightedResampleFromMap,
        "Unresampling operation");
}

#endif