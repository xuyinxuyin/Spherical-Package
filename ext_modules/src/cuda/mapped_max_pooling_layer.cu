#include <torch/extension.h>

#include <vector>

#include "cuda/mapped_max_pool.cuh"

namespace spherical {

namespace cuda {

std::vector<torch::Tensor> MappedMaxPoolForward(
    torch::Tensor input, torch::Tensor sample_map, int kernel_size,
    InterpolationType interpolation) {
  // Useful dimensions to have
  const int64_t batchSize    = input.size(0);
  const int64_t channels     = input.size(1);
  const int64_t inputHeight  = input.size(2);
  const int64_t inputWidth   = input.size(3);
  const int64_t outputHeight = sample_map.size(0);
  const int64_t outputWidth  = sample_map.size(1);

  // Initialize output and index mask
  torch::Tensor output = torch::zeros(
      {batchSize, channels, outputHeight, outputWidth}, input.options());
  torch::Tensor indices =
      torch::zeros({batchSize, channels, outputHeight, outputWidth},
                   input.options().dtype(torch::kLong));

  // Call the CUDA kernel once per batch
  for (int b = 0; b < batchSize; b++) {
    MappedMaxPool2DLauncher(input[b], sample_map, channels, inputHeight,
                            inputWidth, outputHeight, outputWidth, kernel_size,
                            interpolation, output[b], indices[b]);
  }

  return {output, indices};
}

torch::Tensor MappedMaxPoolBackward(torch::Tensor grad_output,
                                    torch::Tensor idx_mask,
                                    torch::Tensor sample_map, int inputHeight,
                                    int inputWidth, int kernel_size,
                                    InterpolationType interpolation) {
  // Useful dimensions to have
  const int64_t batchSize    = grad_output.size(0);
  const int64_t channels     = grad_output.size(1);
  const int64_t outputHeight = grad_output.size(2);
  const int64_t outputWidth  = grad_output.size(3);

  // Initialize output and index mask
  torch::Tensor grad_input = torch::zeros(
      {batchSize, channels, inputHeight, inputWidth}, grad_output.options());

  // Call the CUDA kernel once per batch
  for (int b = 0; b < batchSize; b++) {
    MappedMaxUnpool2DLauncher(grad_output[b], idx_mask[b], sample_map,
                              channels, inputHeight, inputWidth, outputHeight,
                              outputWidth, kernel_size, interpolation,
                              grad_input[b]);
  }

  return grad_input;
}

}  // namespace cuda

}  // namespace spherical